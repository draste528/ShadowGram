#pragma once
#include "Contracts/IMessageRepository.h"
#include <pqxx/pqxx>
#include <memory>
#include <string>

namespace Repositories
{
	class PostgresMessageRepository : public Contracts::IMessageRepository
	{
	private:
		std::shared_ptr<pqxx::connection> m_dbConnection;

		// convert methods fo DB
		std::string ContentTypeToString(Entities::ContentType type);
		Entities::ContentType StringToContentType(const std::string& str);

	public:
		explicit PostgresMessageRepository(std::shared_ptr<pqxx::connection> connection);

		// main save method
		bool SaveMessage(const Entities::Message& message) override;
	};
}