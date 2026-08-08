import socket
import struct
import json

def test_shadowgram():
    HOST = '127.0.0.1'
    PORT = 54321
    
    # ВАЖНО: Возьми существующий chat_id из своей таблицы chats!
    # Если таблица пустая, INSERT в базу упадет из-за Foreign Key.
    # Для теста можно создать чат в PGAdmin: 
    # INSERT INTO chats (type, chat_name) VALUES ('private', 'Test Chat') RETURNING chat_id;
    CHAT_ID = "00000000-0000-0000-0000-000000000000" # Замени на реальный из БД

    message_payload = {
        "type": "send_message",
        "chat_id": CHAT_ID, 
        "content": "Привет, это тестовое сообщение из Python!",
        "nonce": "test_nonce_123"
    }
    
    payload_bytes = json.dumps(message_payload).encode('utf-8')
    
    # Формируем заголовок: 4 байта (длина), сетевой порядок (Big-Endian)
    header = struct.pack('!I', len(payload_bytes))
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(f"[*] Подключение к {HOST}:{PORT}...")
            s.connect((HOST, PORT))
            
            # Отправка
            s.sendall(header + payload_bytes)
            print("[+] Сообщение отправлено. Ожидание ответа...")
            
            # Чтение ответа (сначала 4 байта длины)
            resp_header = s.recv(4)
            if resp_header:
                resp_len = struct.unpack('!I', resp_header)[0]
                resp_body = s.recv(resp_len)
                print(f"[!] Ответ сервера: {resp_body.decode('utf-8')}")
            else:
                print("[-] Сервер разорвал соединение без ответа.")
                
    except Exception as e:
        print(f"[-] Ошибка: {e}")

if __name__ == "__main__":
    test_shadowgram()