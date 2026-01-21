#pragma once
#include <string>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>

namespace Services {
	class ConfigManager {
	private:
		ConfigManager() = default;
		nlohmann::json m_data;

	public :
		static ConfigManager& getInstance() {
			static ConfigManager instance;
			return instance;
		}

		// RESTRICT copying
		ConfigManager(const ConfigManager&) = delete;
		ConfigManager& operator = (const ConfigManager&) = delete;

		bool load(const std::string& path) {
			std::ifstream file(path);
			if (!file.is_open()) return false;
			try
			{
				file >> m_data;
			}
			catch (const nlohmann::json::parse_error& e)
			{
				std::cerr << "[ConfigManager] failed to read json file" << std::endl;
				return false;
			}
			
			return true;
		}

		std::string getDBConnectionString() const {
			return m_data.at("database").at("connection_string").get<std::string>();
		}
	};
}