CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- DELETING OLD TABLES
--DROP TABLE IF EXISTS message_reactions CASCADE;
--DROP TABLE IF EXISTS message_statuses CASCADE;
--DROP TABLE IF EXISTS chat_join_requests CASCADE;
--DROP TABLE IF EXISTS devices CASCADE;
--DROP TABLE IF EXISTS contacts CASCADE;
--DROP TABLE IF EXISTS messages CASCADE;
--DROP TABLE IF EXISTS chat_members CASCADE;
--DROP TABLE IF EXISTS chats CASCADE;
--DROP TABLE IF EXISTS users CASCADE;

-- (users)
CREATE TABLE IF NOT EXISTS users (
    user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email         VARCHAR(255) UNIQUE,
    phone_number  VARCHAR(20) UNIQUE,
    first_name    VARCHAR(100),
    last_name     VARCHAR(100),
    bio           TEXT,
    avatar_url    VARCHAR(255),
    settings      JSONB DEFAULT '{}'::jsonb,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_email_verified BOOLEAN DEFAULT FALSE,
    is_phone_verified BOOLEAN DEFAULT FALSE,
    is_deleted    BOOLEAN DEFAULT FALSE
);

-- (chats)
CREATE TABLE IF NOT EXISTS chats (
    chat_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type          VARCHAR(20) NOT NULL CHECK(type IN ('private', 'group', 'channel')),
    join_type     VARCHAR(20) NOT NULL DEFAULT 'direct' CHECK(join_type IN ('direct', 'by_invite', 'by_request')),
    chat_name     VARCHAR(100),
    chat_username VARCHAR(50) UNIQUE,
    description   TEXT,
    avatar_url    VARCHAR(255),
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_deleted    BOOLEAN DEFAULT FALSE
);

-- (chat_members)
CREATE TABLE IF NOT EXISTS chat_members (
    chat_id   UUID NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    user_id   UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role      VARCHAR(20) NOT NULL CHECK(role IN ('member', 'admin', 'creator')),
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (chat_id, user_id)
);

-- (messages)
CREATE TABLE IF NOT EXISTS messages (
    message_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id      UUID NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    sender_id    UUID REFERENCES users(user_id) ON DELETE SET NULL,
    -- content
    content      BYTEA NOT NULL,
    content_type VARCHAR(50) NOT NULL DEFAULT 'unknown',
    encryption_nonce BYTEA NOT NULL,
    mime_type VARCHAR(100),
    file_size BIGINT,
    -- metadata
    reply_to_message_id UUID references messages(message_id) ON DELETE SET NULL,
    sent_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_edited    BOOLEAN DEFAULT FALSE,
    is_deleted   BOOLEAN DEFAULT FALSE
);

-- (contacts)
CREATE TABLE IF NOT EXISTS contacts (
    owner_user_id   UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    contact_user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    custom_name     VARCHAR(100),
    added_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (owner_user_id, contact_user_id)
);

-- (devices)
CREATE TABLE IF NOT EXISTS devices (
    device_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    public_key    TEXT NOT NULL,
    auth_token    VARCHAR(255) UNIQUE NOT NULL,
    push_token TEXT,
    device_name   VARCHAR(100),
    ip_address    VARCHAR(45),
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_active   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- (chat_join_requests)
CREATE TABLE IF NOT EXISTS chat_join_requests (
    request_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id       UUID NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE, 
    status        VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
    requested_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolver_id   UUID REFERENCES users(user_id),
    resolved_at   TIMESTAMP WITH TIME ZONE,
    UNIQUE(chat_id, user_id) 
);

-- (message_status)
create table if not exists message_statuses (
	message_id UUID NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
	user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
	status VARCHAR(20) NOT NULL CHECK (status IN ('delivered', 'read')),
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
	PRIMARY KEY (message_id, user_id)
);

-- (message_reactions)
CREATE TABLE IF NOT EXISTS message_reactions (
	message_id UUID NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
	user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
	reaction_code VARCHAR(32) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE  DEFAULT NOW(),
	PRIMARY KEY (message_id, user_id)
);

-- 
CREATE INDEX IF NOT EXISTS idx_messages_on_chat_and_time ON messages(chat_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_chat_members_on_user ON chat_members(user_id);
CREATE INDEX IF NOT EXISTS idx_devices_on_user ON devices(user_id);
CREATE INDEX IF NOT EXISTS idx_join_requests_on_chat ON chat_join_requests(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_msg_status_user ON message_statuses(user_id, status);
CREATE INDEX IF NOT EXISTS idx_message_reactions_id ON message_reactions(message_id);
