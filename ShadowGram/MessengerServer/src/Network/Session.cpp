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
	asio::awaitable<void> Session::client_session(asio::ip::tcp::socket socket, std::shared_ptr<Contracts::IAuthService> authService)
	{
		try {
			// +++ TEMPORARY +++ (then will call AuthService::VerifyToken)

			// +++ UUID GENERATION 
			auto authenticatedUserId =  Session::generate_uuid(); // also used for msg uuid

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

				try
				{
					auto request = nlohmann::json::parse(jsonPayload);
					std::string action = request.value("type", "unknown"); // if no type - then unkwown

					if (action == "send_message") {
						// ===== Message Processing

						auto chatOptional = uuids::uuid::from_string(request.value("chat_id", ""));
						if (!chatOptional.has_value()) {
							std::cerr << "[Logic] Invalid Chat UUID." << std::endl;
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

						// Saving to DB
						bool isSaved = messageRepository.SaveMessage(msg);

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
				}
				catch (const nlohmann::json::exception& e)
				{
					std::cerr << "[Security] Corrupt JSON ignored: " << e.what() << std::endl;
				}

			}
		}
		catch (const std::exception& e) {
			std::cerr << "[Session] Connection closed: " << e.what() << std::endl;
		}
	}
}