#include "Network/Server.h"
#include "Network/Session.h"
#include <iostream>

namespace Network
{
	using namespace asio::experimental::awaitable_operators;

	Server::Server(asio::io_context& io_context, unsigned short port)
		: m_ioContext(io_context),
		m_acceptor(io_context, asio::ip::tcp::endpoint(asio::ip::tcp::v4(), port))
	{
		asio::co_spawn(m_ioContext, this->listener(),asio::detached);
	}

	Server::Server(asio::io_context& io_context, unsigned short port,
		std::shared_ptr<Contracts::IAuthService> authService) :
		m_ioContext(io_context),
		m_acceptor(io_context, asio::ip::tcp::endpoint(asio::ip::tcp::v4(), port)),
		m_authService(std::move(authService))
	{
		asio::co_spawn(m_ioContext, this->listener(), asio::detached);
	}

	asio::awaitable<void> Server::listener()
	{
		try {
			while (true) {
				asio::ip::tcp::socket socket = co_await m_acceptor.async_accept(asio::make_strand(m_ioContext));
				std::cout << "[Server] New client connected: " << socket.remote_endpoint() << std::endl;
				asio::co_spawn(m_ioContext, Session::client_session(std::move(socket)), asio::detached);
			}
		}
		catch (const std::exception& e) {
			std::cerr << "[Listener] Exception: " << e.what() << std::endl;
		}
	}
	
	
}

