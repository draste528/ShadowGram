#include "Services/AuthService.h"
#include "Entities/User.h"
#include "argon2.h"
#include <iostream>
#include <chrono>
#include <stduuid/uuid.h>

namespace Services
{
	AuthService::AuthService(std::shared_ptr<Contracts::IUserRepository> userRepository)
		: m_userRepository(std::move(userRepository))
	{
		// just save dependenses
	}

	// --- Register Logic ---
	Contracts::AuthResult AuthService::RegisterUser(
		const std::string& username,
		const std::string& password,
		const std::string& first_name)
	{
		Contracts::AuthResult result;

		// Checking if User exist
		auto existingUser = m_userRepository->GetUserByUsername(username);
		if (existingUser.has_value())
		{
			result.success = false;
			result.error_message = "Username already taken";
			return result;
		}

		// --- HashingPasswod (Argon2id) (C-style) --- 
		// (with simple parametrs for speed)
		std::cout << "[AuthService] Hashing new password for user [" << username << "] ..." << std::endl;

		// buffer for encoded hash
		char encoded_hash[128];

		// TODO: create unique salt for every user
		std::string salt = "stoletnyaya_salt";

		int hash_res = argon2id_hash_encoded(
			2, // t_cost: iterarions
			65536, // m_cost: memory
			1, // parallelism: threads
			password.c_str(), password.length(),
			salt.c_str(), salt.length(),
			32, // desired size of raw hash
			encoded_hash, 128
		);

		if (hash_res != ARGON2_OK) {
			std::cerr << "[AuthService] Argon2 hashing failed (with error code): " << hash_res << std::endl;
			result.success = false;
			result.error_message = "Internal server error during hashing.";
			return result;
		}

		// creating string PASSWORD HASH (with encode hash)
		std::string password_hash(encoded_hash);


		// Preparing DATA for a new User
		Entities::User newUser;
		
		// +++ UUID Generation
		std::random_device randDevice;
		std::mt19937 generator( randDevice() );
		uuids::uuid_random_generator uuidGen( generator );
		newUser.user_id = uuidGen(); 

		newUser.username = username;
		newUser.password_hash = password_hash;
		newUser.first_name = first_name;
		newUser.created_at = std::chrono::system_clock::now();
		newUser.last_seen = std::chrono::system_clock::now();
		newUser.settings_json = "{}"; // default JSON

		// Sendong to Repository 
		bool created = m_userRepository->CreateUser(newUser);

		if (created)
		{
			std::cout << "[AuthService] New user registered: " << username << std::endl;
			result.success = true;
			result.user_id = newUser.user_id;
		}
		else
		{
			result.success = false;
			result.error_message = "Failed to save user to database.";
		}

		return result;

	}


	// --- Login Logic ---
	Contracts::AuthResult AuthService::LoginUser(
		const std::string& username,
		const std::string& password)
	{
		Contracts::AuthResult result;

		// Searching for User
		auto user = m_userRepository->GetUserByUsername(username);
		if (!user.has_value())
		{
			result.success = false;
			result.error_message = "Invalid username or password";
			return result;
		}

		// Checking password
		std::cout << "[AuthService]  Verifyingg password for " << username << "..." << std::endl;


		// verify() function retrieve m, t, p , salt and comparing password_hashes
		int verify_code = argon2id_verify(
			user->password_hash.c_str(),
			password.c_str(),
			password.length()
		);


		if (verify_code == ARGON2_OK)
		{
			//Success
			std::cout << "[AuthService] Login successful for " << username << std::endl;
			result.success = true;
			result.user_id = user->user_id;
			// TODO: generate JWT token here
		}
		else
		{
			// Wrong Password
			std::cout << "[AuthService] Invalid password for " << username << std::endl;
			result.success = false;
			result.error_message = "Invalid username or password";
		}

		return result;
	}

}