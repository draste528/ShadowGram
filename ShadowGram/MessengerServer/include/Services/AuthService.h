#pragma once

#include "Contracts/IAuthService.h"
#include "Contracts/IUserRepository.h"
#include <memory>

namespace Services
{
	class AuthService : public Contracts::IAuthService
	{
	private:
		std::shared_ptr<Contracts::IUserRepository> m_userRepository;

	public:
		explicit AuthService(std::shared_ptr<Contracts::IUserRepository> userRepository);
		
		// --- IAuthService (contrsct realisation) ---

		Contracts::AuthResult RegisterUser(
			const std::string& username,
			const std::string& password,
			const std::string& first_name) override;

		Contracts::AuthResult LoginUser(
			const std::string& username,
			const std::string& password) override;

	};
}