#include <iostream>
#include <exception>
#include <memory>  // for shared_ptr
#include <asio.hpp>
#include <pqxx/pqxx>  // for pqxx connection

#include "Network/Server.h"
#include "Contracts/IAuthService.h"
#include "Contracts/IUserRepository.h"
#include "Services/AuthService.h"
#include "Repositories/PostgresUserRepository.h"
#include "Services/ConfigManager.h" // extracting config for DB

int main() {

	// ====== Loading Configuration =====
	if (!Services::ConfigManager::getInstance().load("config.json")) {
		std::cerr << "[Main] FATAL: Couldn't load config.json" << std::endl;
		std::cerr << "Make sure the file exist if folder. " << std::endl;
		return 1;
	}

	// exstracting settings via ConfigManager
	const std::string db_connection_string = Services::ConfigManager::getInstance().getDBConnectionString();

	// TODO : add getPort() to ConfigManager
	const unsigned short port = 54321;

	try
	{
		asio::io_context io_context;

		// --- 1. Repository level ---
		// --- Estabilishing connection with DB ---
		auto db_connection = std::make_shared<pqxx::connection>(db_connection_string);
		std::cout << "[Main] Database connection successful." << std::endl;

		// Creating Storekipper and trunsfer connection to him
		auto user_repo = std::make_shared<Repositories::PostgresUserRepository>(db_connection);

		// --- 2. Service (Logic) level ---
		// Creating Chief and giving Storekipper to him
		auto auth_service = std::make_shared<Services::AuthService>(user_repo);

		// --- 3. Network level ---
		//  Creating Server and giving Chief to him
		Network::Server server(io_context, port, auth_service);

		// --- Running ---
		std::cout << "[Server] Running on port: " << port << "..." << std::endl;
		io_context.run();
	}
	catch (const pqxx::broken_connection& e)
	{
		std::cerr << "[Main] FATAL: Database connection failed: " << e.what() << std::endl;
		std::cerr << "		Chek connection or if PostgreSQL is running." << std::endl;
	}
	catch (const std::exception& e)
	{
		std::cerr << "[Main] FATAL: " << e.what() << std::endl;
	}

	return 0;
}