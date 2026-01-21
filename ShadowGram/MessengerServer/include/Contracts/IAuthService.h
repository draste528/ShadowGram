#pragma once 

#include <string>
#include <optional>
#include <stduuid/uuid.h>

namespace Contracts
{
	struct AuthResult
	{
		bool success = false;
		std::string error_message;

		std::optional<uuids::uuid> user_id;
	};

	class IAuthService
	{
	public:

		virtual ~IAuthService() = default;

		virtual AuthResult RegisterUser(const std::string& user_name, const std::string& password, const std::string& first_name) = 0;

		virtual AuthResult LoginUser(const std::string& username, const std::string& password) = 0;
	};
}