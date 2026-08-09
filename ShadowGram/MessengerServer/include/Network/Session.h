#pragma once
#include <asio.hpp>
#include <stduuid/uuid.h>
#include <random>
#include "Contracts/IAuthService.h"
#include <memory>

namespace Network
{
	class Session {
	private:
		// +++ UUID GENERATION 
		// *** (Thread_safe UUID Generation using thread_local)
		static uuids::uuid generate_uuid() {
			static thread_local std::random_device randDevice;
			static thread_local std::mt19937 generator{ randDevice() };
			static thread_local uuids::uuid_random_generator uuidGen{ generator };
			return uuidGen();
		}

		// Writes one length-prefixed frame.  `body` is taken by value on
		// purpose: a reference parameter would dangle, because the argument is
		// usually a temporary from json::dump() that dies at the end of the
		// full-expression while this coroutine is still suspended.
		static asio::awaitable<void> write_frame(asio::ip::tcp::socket& socket, std::string body);

	public:
		static asio::awaitable<void> client_session(asio::ip::tcp::socket socket, std::shared_ptr<Contracts::IAuthService> authService);
	};
}