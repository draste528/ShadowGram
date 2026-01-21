## ShadowGram 

Shadowgram is a secure messaging system. (work-in-progress)

The project is designed as "full messenger" , consisting of:
- **C++ backend server**
- **client application (planned on Java)**

This repository contains both parts to simplify development.

This Project(learning) is primarily focused on:
- backend architechture
- networking
- database design
- security-aware system design


**Project Structure**:
ShadowGram/
   MessengerServer/ # C++ backend server
     include/
       Entities # Core domain models
       Repositories # Database access layer
       Services # Business logic
       Network # TCP server & sessions
     src/

     CMakeLists.txt

   MessengerClient/ # Client application (planned, Java)

   db_init.sql # PostgreSQL schema
   CMakeLists.txt
   CMakePresets.json
   vcpkg.json


The Server follows a **layered architecture**:
- **Network layer** - handles TCP connections and sessions
- **Service layer** - contains business logic
- **Repository layer** - responsible for database interaction
- **Entities** - objects (user, message, ...)




## Security (Current State)

ShadowGram is designed with security considerations from the start.

### Implemented / Planned Concepts
- Server-side authentication
- Separation of network, logic, and data layers
- Prepared structure for encrypted message handling
- Secure password storage (hashing)

### Planned (Not Fully Implemented Yet)
- End-to-end encryption
- Secure key exchange
- Message signing and verification
- Device-level trust and session validation



## Tech Stack

### Backend (Server)
- C++20
- Boost.Asio
- PostgreSQL
- CMake
- vcpkg

### Client (Planned)
- Java
