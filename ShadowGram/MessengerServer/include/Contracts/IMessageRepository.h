#pragma once 
#include "Entities/Message.h"

namespace Contracts
{
	class IMessageRepository
	{
	public:
		virtual ~IMessageRepository() = default;
		virtual bool SaveMessage(const Entities::Message& message) = 0;
	};
}