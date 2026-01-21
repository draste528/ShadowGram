#pragma once
#include <stduuid/uuid.h>
#include <string>
#include <chrono>
#include <optional>
#include <vector>

namespace Entities
{
	// message types
	enum class ContentType
	{
		Unknown,
		Text,
		Image, // mb later
		Video, // mb later
		Audio,
		Voice,
		File, // mb later
		ServiceInfo
	};

	struct Message
	{
		uuids::uuid message_id;
		uuids::uuid chat_id;
		std::optional<uuids::uuid> sender_id; // might be null (user left the chat)

		// content - BYTEA
		std::vector<uint8_t> content;
		ContentType content_type = ContentType::Unknown; // Unknown - default
		std::vector<uint8_t> encryption_nonce;

		// metadata
		std::optional<std::string> mime_type;
		std::optional<long long> file_size;
		std::optional<uuids::uuid> reply_to_message_id;

		std::chrono::system_clock::time_point sent_at;
		bool is_edited = false;
		bool is_deleted = false;
	};
}