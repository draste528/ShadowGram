#include "Network/Session.h"
#include "Repositories/PostgresMessageRepository.h"
#include "Services/ConfigManager.h"
#include <iostream>
#include <vector>
#include <nlohmann/json.hpp>
#include <stduuid/uuid.h>
#include <asio/detail/socket_ops.hpp>

// keep in mind
using json = nlohmann::json;

namespace Network
{
	// One rejected request produces exactly one error frame.  The code is the
	// stable part a client may branch on; the message is for a human reading a
	// log and never echoes anything the client sent.
	namespace
	{
		json make_error(const char* code, const char* message)
		{
			return json{
				{"type", "error_response"},
				{"status", "error"},
				{"code", code},
				{"message", message}
			};
		}
	}

	asio::awaitable<void> Session::write_frame(asio::ip::tcp::socket& socket, std::string body)
	{
		uint32_t networkLength = asio::detail::socket_ops::host_to_network_long(
			static_cast<uint32_t>(body.size())
		);

		co_await asio::async_write(socket, asio::buffer(&networkLength, 4), asio::use_awaitable);
		co_await asio::async_write(socket, asio::buffer(body), asio::use_awaitable);
	}

	asio::awaitable<void> Session::client_session(asio::ip::tcp::socket socket, std::shared_ptr<Contracts::IAuthService> authService)
	{
		try {
			// No identity until the connection has authenticated (see F-02 login).
			std::optional<uuids::uuid> authenticatedUserId;

			const std::string dbConnectionStr = Services::ConfigManager::getInstance().getDBConnectionString();
			auto dbConnection = std::make_shared<pqxx::connection>(dbConnectionStr);
			Repositories::PostgresMessageRepository messageRepository(dbConnection);

			while (true) {
				// ===== Readin HEADER 
				uint32_t networkMessageLength = 0;

				// Reading TIMEOUT *** (Slowloris Protection) 
				co_await asio::async_read(socket,
					asio::buffer(&networkMessageLength, sizeof(networkMessageLength)),
					asio::use_awaitable);

				// network to host order of bytes
				uint32_t bodyLength = asio::detail::socket_ops::network_to_host_long(networkMessageLength);

				// *** (Overflow Protection) 1MB limit
				if (bodyLength > 1024 * 1024) {
					std::cerr << "[Security] Giant packet blocked. Closing connection." << std::endl;
					co_return;
				}

				// ===== Reading BODY
				std::string jsonPayload; // usefull load
				jsonPayload.resize(bodyLength);
				co_await asio::async_read(socket,
					asio::buffer(jsonPayload),
					asio::use_awaitable);

				std::optional<json> rejection;

				try
				{
					auto request = nlohmann::json::parse(jsonPayload);

					if (!request.is_object()) {
						co_await Session::write_frame(socket, make_error(
							"invalid_request", "Request body must be a JSON object.").dump());
						continue;
					}

					std::string action = request.value("type", "unknown"); // if no type - then unkwown

					if (action == "send_message") {
						// ===== Message Processing

						auto chatOptional = uuids::uuid::from_string(request.value("chat_id", ""));
						if (!chatOptional.has_value()) {
							std::cerr << "[Logic] Invalid Chat UUID." << std::endl;
							co_await Session::write_frame(socket, make_error(
								"invalid_chat_id", "chat_id is missing or not a UUID.").dump());
							continue;
						}

						// *** (Checking Access Rights) 
						// TODO

						// Message creation
						Entities::Message msg;
						msg.message_id = Session::generate_uuid(); // generate unique messge_id (UUID)
						msg.chat_id = chatOptional.value();

						// *** (Tacking sender_id from Session, not JSON)
						msg.sender_id = authenticatedUserId;

						// Reading Content (Base64 in future)
						std::string contentStr = request.value("content", "");
						msg.content.assign(contentStr.begin(), contentStr.end());

						// Reading Nonce (encryption)
						std::string nonceStr = request.value("nonce", "");
						msg.encryption_nonce.assign(nonceStr.begin(), nonceStr.end());

						// An unauthenticated connection has no sender to store, so the
						// request is refused before it can reach the database.
						bool isSaved = false;
						if (msg.sender_id.has_value())
						{
							// Saving to DB
							isSaved = messageRepository.SaveMessage(msg);
						}
						else
						{
							std::cerr << "[Auth] send_message on an unauthenticated connection refused." << std::endl;
						}

						// ===== Response to Sender
						json response = {
							{"type", "response"},
							{"status", isSaved ? "ok" : "error"},
							{"message_id", uuids::to_string(msg.message_id)}
						};

						std::string responseStr = response.dump();
						uint32_t responseNetworkLength = asio::detail::socket_ops::host_to_network_long(
							static_cast<uint32_t>(responseStr.size())
						);

						co_await asio::async_write(socket, asio::buffer(&responseNetworkLength, 4),
							asio::use_awaitable);
						co_await asio::async_write(socket, asio::buffer(responseStr), 
							asio::use_awaitable);
					}
					else if (action == "register") {
						std::string username = request.value("username", "");
						std::string password = request.value("password", "");
						std::string first_name = request.value("first_name", "");

						// Вызываем логику AuthService
						auto authResult = authService->RegisterUser(username, password, first_name);

						// Формируем ответ
						json response = {
							{"type", "register_response"}
						};

						if (authResult.success) {
							response["status"] = "ok";
							response["user_id"] = uuids::to_string(authResult.user_id.value());
						}
						else {
							response["status"] = "error";
							response["message"] = authResult.error_message;
						}

						// Отправка ответа клиенту
						std::string responseStr = response.dump();
						uint32_t responseNetworkLength = asio::detail::socket_ops::host_to_network_long(
							static_cast<uint32_t>(responseStr.size())
						);

						co_await asio::async_write(socket, asio::buffer(&responseNetworkLength, 4), asio::use_awaitable);
						co_await asio::async_write(socket, asio::buffer(responseStr), asio::use_awaitable);

					}
					else if (action == "login") {
						std::string username = request.value("username", "");
						std::string password = request.value("password", "");

						auto authResult = authService->LoginUser(username, password);

						json response = {
							{"type", "login_response"}
						};

						if (authResult.success) {
							// The identity is bound to this connection; a later successful
							// login replaces it, a failed one leaves it untouched.
							authenticatedUserId = authResult.user_id;
							response["status"] = "ok";
							response["user_id"] = uuids::to_string(authResult.user_id.value());
						}
						else {
							response["status"] = "error";
							response["message"] = authResult.error_message;
						}

						std::string responseStr = response.dump();
						uint32_t responseNetworkLength = asio::detail::socket_ops::host_to_network_long(
							static_cast<uint32_t>(responseStr.size())
						);

						co_await asio::async_write(socket, asio::buffer(&responseNetworkLength, 4), asio::use_awaitable);
						co_await asio::async_write(socket, asio::buffer(responseStr), asio::use_awaitable);
					}
					else {
						co_await Session::write_frame(socket, make_error(
							"unknown_action", "Unsupported value for the type field.").dump());
					}
				}
				catch (const nlohmann::json::parse_error& e)
				{
					std::cerr << "[Security] Corrupt JSON: " << e.what() << std::endl;
					rejection = make_error("invalid_json", "Request body is not valid JSON.");
				}
				catch (const nlohmann::json::type_error& e)
				{
					std::cerr << "[Security] Wrongly typed field: " << e.what() << std::endl;
					rejection = make_error("invalid_field", "A field has the wrong JSON type.");
				}
				catch (const nlohmann::json::exception& e)
				{
					std::cerr << "[Security] Rejected request: " << e.what() << std::endl;
					rejection = make_error("invalid_request", "Request could not be processed.");
				}

				// co_await cannot appear inside a handler, so the frame for an
				// exception is written here instead.
				if (rejection.has_value()) {
					co_await Session::write_frame(socket, rejection->dump());
				}

			}
		}
		catch (const std::exception& e) {
			std::cerr << "[Session] Connection closed: " << e.what() << std::endl;
		}
	}
}