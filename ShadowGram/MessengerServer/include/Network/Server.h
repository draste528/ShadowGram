#pragma once

#include <asio.hpp>
#include <asio/experimental/awaitable_operators.hpp>
#include <memory>
#include "Contracts/IAuthService.h"

namespace Network
{
	class Server {
	private:
		asio::awaitable<void> listener();
		asio::io_context& m_ioContext;
		asio::ip::tcp::acceptor m_acceptor;
		// Server owing Service
		std::shared_ptr<Contracts::IAuthService> m_authService;

	public:
		Server(asio::io_context& io_context, unsigned short port);
		Server(asio::io_context& io_context, unsigned short port,
			std::shared_ptr<Contracts::IAuthService> authService);
	};
}