#pragma once
#include <stduuid/uuid.h>
#include <optional>
#include <chrono>
#include <string>


namespace Entities
{
	struct User
	{
		uuids::uuid user_id;
		std::string username;
        std::string password_hash; //argon
        std::string first_name;

        std::optional<std::string> email;
        std::optional<std::string> phone_number;
        std::optional<std::string> last_name;
        std::optional<std::string> bio;
        std::optional<std::string> avatar_url; //avatar

        std::string settings_json;

        std::chrono::system_clock::time_point created_at;
        std::chrono::system_clock::time_point last_seen;

        bool is_email_verified = false;
        bool is_phone_verified = false;
        bool is_deleted = false;


	};
}
