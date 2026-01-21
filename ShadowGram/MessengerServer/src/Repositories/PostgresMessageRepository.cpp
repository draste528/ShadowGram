#include "Repositories/PostgresMessageRepository.h"
#include <iostream>
#include <stduuid/uuid.h>
#include "Utils/TimeUtils.h"

namespace Repositories
{
	PostgresMessageRepository::PostgresMessageRepository(std::shared_ptr<pqxx::connection> connection)
		: m_dbConnection(std::move(connection)) { }

	//--- Type Convertation ----
	std::string PostgresMessageRepository::ContentTypeToString(Entities::ContentType type)
	{
		switch (type)
		{
		case Entities::ContentType::Text: return "text";
		case Entities::ContentType::Image: return "image";
		case Entities::ContentType::Video: return "video";
		case Entities::ContentType::Audio: return "audio";
		case Entities::ContentType::Voice: return "voice";
		case Entities::ContentType::File: return "file";
		case Entities::ContentType::ServiceInfo: return "serviceInfo";
		default: return "unknown";
		}
	}

	// TEMPORARY method for Nonce GENERATION (while client don't send it)
	std::vector<uint8_t> GenerateDummyNonce() {
		std::vector<uint8_t> nonce(12);
		std::random_device rd;
		std::generate(nonce.begin(), nonce.end(), std::ref(rd));
		return nonce;
	}

	Entities::ContentType PostgresMessageRepository::StringToContentType(const std::string& str)
	{
		if (str == "text") return Entities::ContentType::Text;
		if (str == "image") return Entities::ContentType::Image;
		if (str == "video") return Entities::ContentType::Video;
		if (str == "audio") return Entities::ContentType::Audio;
		if (str == "voice") return Entities::ContentType::Voice;
		if (str == "file") return Entities::ContentType::File;
		if (str == "serviceInfo") return Entities::ContentType::ServiceInfo;

		// Unknown - default
		return Entities::ContentType::Unknown;
	}

	// --- Saving Message ---
	bool PostgresMessageRepository::SaveMessage(const Entities::Message& msg)
	{
		try
		{
			pqxx::work txn(*m_dbConnection);

			// SQL injection PROTECTION
			std::string sql = "INSERT INTO messages (message_id, chat_id, sender_id, content, content_type, "
				"encryption_nonce, mime_type, file_size, reply_to_message_id, sent_at) "
				"VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())";
			
			// if Nonse is empty - generate random one
			std::vector<uint8_t> nonce_to_save = msg.encryption_nonce;
			if (msg.encryption_nonce.empty()) {
				nonce_to_save = GenerateDummyNonce();
			}

			pqxx::binarystring content_blob(msg.content.data(), msg.content.size());
			pqxx::binarystring nonce_blob(nonce_to_save.data(), nonce_to_save.size());

			txn.exec_params(sql,
				uuids::to_string(msg.message_id),
				uuids::to_string(msg.chat_id),
				msg.sender_id ? std::make_optional(uuids::to_string(*msg.sender_id)) : std::nullopt,
				content_blob, 
				ContentTypeToString(msg.content_type),
				nonce_blob,
				msg.mime_type,
				msg.file_size,
				msg.reply_to_message_id ? std::make_optional(uuids::to_string(*msg.reply_to_message_id)) : std::nullopt
			);

			txn.commit();
			std::cout << "[Repo] Message saved: " << msg.message_id << std::endl;
			return true;

			
		}
		catch (const std::exception& e)
		{
			std::cerr << "[Repo] SaveMessage Error: " << e.what() << std::endl;
			return false;
		}
	}
}