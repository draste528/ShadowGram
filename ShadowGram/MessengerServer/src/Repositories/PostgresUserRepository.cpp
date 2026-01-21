#include "Repositories/PostgresUserRepository.h"
#include <pqxx/pqxx> // for perfoming transactions
#include <iostream>
#include <stduuid/uuid.h> // for convertations UUID to string
#include <string>
#include <chrono>
#include "Utils/TimeUtils.h"


namespace Repositories
{
	PostgresUserRepository::PostgresUserRepository(std::shared_ptr<pqxx::connection> dbConnection)
		: m_dbConnection(std::move(dbConnection))
	{

		if (!m_dbConnection || !m_dbConnection->is_open())
		{
			throw std::runtime_error("PostgresUserRepository: Database Connection is not valid.");
		}
		std::cout << "[Repo] PostgresUserRepository initialized." << std::endl;
	}

	// --- CreateUser realization (with SQL) ---
	bool PostgresUserRepository::CreateUser(const Entities::User& user)
	{
		try
		{
			// starting tranzaction (safe operation)
			pqxx::work txn(*m_dbConnection);

			// SQL query
			std::string sql =
				"INSERT INTO users (user_id, username, password_hash, first_name, "
				"created_at, last_seen, settings) "
				"VALUES ($1, $2, $3, $4, $5, $6, $7)";

			// converting data for libpqxx
			std::string user_id_str = uuids::to_string(user.user_id);
			std::string created_at_str = Utils::Time::to_pg_timestamp(user.created_at);
			std::string last_seen_str = Utils::Time::to_pg_timestamp(user.last_seen);

			txn.exec_params(sql,
				user_id_str, //$1
				user.username,  //$2
				user.password_hash,  //$3
				user.first_name,  //$4
				created_at_str,  //$5 
				last_seen_str,  //$6 
				user.settings_json  //$7
			);

			// ending transaction 
			txn.commit();

			std::cout << "[Repo] SQL INSERT successful for user: " << user.username << std::endl;
			return true;

		}
		catch (const std::exception& e)
		{
			// if smth went wrong (username already taken)
			// txt.commit() wouldn't be released , 
			// and tranzaction will be rolled back
			std::cerr << "[Repo] SQL INSERT failed: " << e.what() << std::endl;
			return false;
		}
	}

	// --- User Building from DB answer ---
	namespace { // Anonymus namespace
		Entities::User MapRowToUser(const pqxx::row& row)
		{
			Entities::User user;

			// convert UUID from db to stduuid object
			user.user_id = uuids::uuid::from_string(row["user_id"].as<std::string>()).value();

			user.username = row["username"].as<std::string>();
			user.password_hash = row["password_hash"].as<std::string>();
			user.first_name = row["first_name"].as<std::string>();

			
			user.created_at = Utils::Time::from_pg_timestamp( row["created_at"].as<std::string>());
			user.last_seen = Utils::Time::from_pg_timestamp(row["last_seen"].as<std::string>());
			
			// processing field that could be NULL
			if (!row["last_name"].is_null())
				user.last_name = row["last_name"].as<std::string>();

			if (!row["email"].is_null())
				user.email = row["email"].as<std::string>();

			if (!row["phone_number"].is_null())
				user.phone_number = row["phone_number"].as<std::string>();

			if (!row["bio"].is_null())
				user.bio = row["bio"].as<std::string>();

			if (!row["avatar_url"].is_null())
				user.avatar_url = row["avatar_url"].as<std::string>();

			user.settings_json = row["settings"].as<std::string>("{}");

			return user;
		}
	}


	// --- GetUserByUsername (with SQL) ---
	std::optional<Entities::User> PostgresUserRepository::GetUserByUsername(const std::string& username)
	{
		try
		{
			// we will use "slow" transaction (read-only)
			pqxx::nontransaction ntxn(*m_dbConnection);

			// SQL query
			std::string sql = "SELECT * FROM users WHERE username = $1 LIMIT 1";

			pqxx::result res = ntxn.exec_params(sql, username);

			// checking result
			if (res.empty()) { 
				return std::nullopt;
			}
				
			return MapRowToUser(res[0]);

		}
		catch (const std::exception& e)
		{
			std::cerr << "[Repo] SQL SELECT (by username) failed: " << e.what() << std::endl;
			return std::nullopt;
		}
	}


	// --- GetUserById (with SQL) ---
	std::optional<Entities::User> PostgresUserRepository::GetUserById(const uuids::uuid& user_id)
	{
		try
		{
			// non transaction (read-only)
			pqxx::nontransaction ntxn(*m_dbConnection);

			// praparing SQL query
			std::string sql = "SELECT * FROM users WHERE user_id = $1 LIMIT 1";

			// converting UUID to string for DB
			std::string user_id_str = uuids::to_string(user_id);

			pqxx::result res = ntxn.exec_params(sql, user_id_str);

			// checking
			if (res.empty()) {
				return std::nullopt;
			}

			return MapRowToUser(res[0]);
		}
		catch (const std::exception& e)
		{
			std::cerr << "[Repo] SQL SELECT (by ID) failed: " << e.what() << std::endl;
			return std::nullopt;
		}
	}
}