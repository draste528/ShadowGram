#pragma once

#include "Entities/User.h"
#include <string>
#include <optional>
#include <stduuid/uuid.h>

namespace Contracts
{
	class IUserRepository
	{
	public:
		virtual ~IUserRepository() = default;

		virtual bool CreateUser(const Entities::User & user) = 0;

		virtual std::optional<Entities::User> GetUserByUsername(
			const std::string & username) = 0;

		virtual std::optional<Entities::User> GetUserById(
			const uuids::uuid& user_id) = 0;
	};
	
}