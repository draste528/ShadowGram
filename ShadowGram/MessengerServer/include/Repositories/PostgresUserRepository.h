#pragma once

#include "Contracts/IUserRepository.h"
#include <pqxx/pqxx>
#include <memory>

namespace Repositories
{
	class PostgresUserRepository : public Contracts::IUserRepository
	{
	private:
		// clever pointer to db connection
		std::shared_ptr<pqxx::connection> m_dbConnection;

	public:
		explicit PostgresUserRepository(std::shared_ptr<pqxx::connection> dbConnection);

		// --- Contract Realization "IUserRepository" ---
		bool CreateUser(const Entities::User& user) override;

		std::optional<Entities::User> GetUserByUsername(
			const std::string& username) override;

		std::optional<Entities::User> GetUserById(
			const uuids::uuid& user_id) override;
	};
}