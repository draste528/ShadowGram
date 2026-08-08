import socket
import json
import struct

def register_test():
    # Настройки подключения
    host = '127.0.0.1'
    port = 54321

    # Данные для регистрации
    registration_data = {
        "type": "register",
        "username": "konstantin_v",
        "password": "super_secret_password",
        "first_name": "Konstantin"
    }

    try:
        # Создаем TCP сокет
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(f"Connecting to {host}:{port}...")
            s.connect((host, port))

            # 1. Подготавливаем JSON
            json_payload = json.dumps(registration_data).encode('utf-8')
            payload_length = len(json_payload)

            # 2. Упаковываем длину в 4 байта (Network byte order - Big Endian)
            # '!I' означает unsigned int в сетевом порядке байт
            header = struct.pack('!I', payload_length)

            # 3. Отправляем заголовок и тело
            s.sendall(header)
            s.sendall(json_payload)
            print(f"Sent registration request ({payload_length} bytes)")

            # 4. Читаем ответ (сначала 4 байта длины)
            response_header = s.recv(4)
            if not response_header:
                print("Server closed connection.")
                return

            response_length = struct.unpack('!I', response_header)[0]
            
            # 5. Читаем тело ответа
            response_body = s.recv(response_length).decode('utf-8')
            response_json = json.loads(response_body)

            print("\nServer response:")
            print(json.dumps(response_json, indent=4))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    register_test()