#pragma once
#include <asio.hpp>
#include <stduuid/uuid.h>
#include <random>

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

	public:
		static asio::awaitable<void> client_session(asio::ip::tcp::socket socket);
	};
}