// Файл: 15_http_server.go
// Навчальний ехо HTTP сервер на Go
// Цей файл демонструє створення простого веб-сервера з різними ендпоінтами

package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"
)

func main() {
	fmt.Println("=== Запуск навчального HTTP сервера ===")
	fmt.Println("Сервер буде доступний за адресою: http://localhost:8080")
	fmt.Println("Доступні ендпоінти:")
	fmt.Println("  GET  /              - головна сторінка")
	fmt.Println("  GET  /hello         - привітання")
	fmt.Println("  GET  /time          - поточний час")
	fmt.Println("  GET  /echo?text=... - ехо-відповідь")
	fmt.Println("  POST /echo          - ехо для POST запитів")
	fmt.Println("  GET  /health        - перевірка здоров'я сервера")
	fmt.Println("  GET  /api/info      - інформація про сервер у JSON форматі")
	fmt.Println()

	// Реєстрація обробників для різних шляхів (ендпоінтів)
	http.HandleFunc("/", homeHandler)
	http.HandleFunc("/hello", helloHandler)
	http.HandleFunc("/time", timeHandler)
	http.HandleFunc("/echo", echoHandler)
	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/api/info", apiInfoHandler)

	// Запуск сервера на порту 8080
	// log.Fatal автоматично логує помилки, якщо сервер не може запуститися
	log.Fatal(http.ListenAndServe(":8080", nil))
}

// homeHandler обробляє головну сторінку
func homeHandler(w http.ResponseWriter, r *http.Request) {
	// Перевіряємо, чи це головна сторінка (шлях "/")
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}

	html := `
<!DOCTYPE html>
<html>
<head>
    <title>Навчальний HTTP сервер на Go</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #333; }
        .endpoint { background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; }
        code { background: #eee; padding: 2px 5px; border-radius: 3px; }
    </style>
</head>
<body>
    <h1>Навчальний HTTP сервер на Go</h1>
    <p>Це простий демонстраційний сервер, створений для навчання основам Go.</p>
    
    <h2>Доступні ендпоінти:</h2>
    <div class="endpoint">
        <strong>GET</strong> <code><a href="/hello">/hello</a></code><br>
        Просте привітання
    </div>
    <div class="endpoint">
        <strong>GET</strong> <code><a href="/time">/time</a></code><br>
        Поточний час сервера
    </div>
    <div class="endpoint">
        <strong>GET</strong> <code><a href="/echo?text=Привіт, світ!">/echo?text=Привіт, світ!</a></code><br>
        Ехо-відповідь для GET запитів
    </div>
    <div class="endpoint">
        <strong>POST</strong> <code>/echo</code><br>
        Ехо-відповідь для POST запитів (використовуйте curl або Postman)
    </div>
    <div class="endpoint">
        <strong>GET</strong> <code><a href="/health">/health</a></code><br>
        Перевірка здоров'я сервера
    </div>
    <div class="endpoint">
        <strong>GET</strong> <code><a href="/api/info">/api/info</a></code><br>
        Інформація про сервер у JSON форматі
    </div>
    
    <h2>Як тестувати:</h2>
    <p>Використовуйте браузер для GET запитів або інструменти на кшталт:</p>
    <ul>
        <li><code>curl http://localhost:8080/hello</code></li>
        <li><code>curl "http://localhost:8080/echo?text=Тест"</code></li>
        <li><code>curl -X POST -d "message=Привіт" http://localhost:8080/echo</code></li>
    </ul>
</body>
</html>`

	// Встановлюємо заголовок Content-Type для HTML
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	
	// Записуємо HTML у відповідь
	fmt.Fprint(w, html)
}

// helloHandler обробляє шлях /hello
func helloHandler(w http.ResponseWriter, r *http.Request) {
	// Перевіряємо метод запиту (має бути GET)
	if r.Method != "GET" {
		http.Error(w, "Метод не підтримується", http.StatusMethodNotAllowed)
		return
	}

	// Встановлюємо заголовок Content-Type
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	
	// Записуємо відповідь
	fmt.Fprintf(w, "Привіт! Це навчальний HTTP сервер на Go.\n")
	fmt.Fprintf(w, "Час на сервері: %s\n", time.Now().Format("15:04:05"))
	fmt.Fprintf(w, "Ваша IP-адреса: %s\n", r.RemoteAddr)
}

// timeHandler обробляє шлях /time
func timeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != "GET" {
		http.Error(w, "Метод не підтримується", http.StatusMethodNotAllowed)
		return
	}

	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	
	// Форматуємо поточний час
	currentTime := time.Now()
	fmt.Fprintf(w, "Поточний час на сервері:\n")
	fmt.Fprintf(w, "  Дата: %s\n", currentTime.Format("02.01.2006"))
	fmt.Fprintf(w, "  Час: %s\n", currentTime.Format("15:04:05"))
	fmt.Fprintf(w, "  Тиждень: %s\n", currentTime.Weekday())
}

// echoHandler обробляє шлях /echo (GET та POST)
func echoHandler(w http.ResponseWriter, r *http.Request) {
	// Обробляємо різні методи запиту
	switch r.Method {
	case "GET":
		echoGetHandler(w, r)
	case "POST":
		echoPostHandler(w, r)
	default:
		http.Error(w, "Метод не підтримується", http.StatusMethodNotAllowed)
	}
}

// echoGetHandler обробляє GET запити до /echo
func echoGetHandler(w http.ResponseWriter, r *http.Request) {
	// Отримуємо параметр "text" з URL
	text := r.URL.Query().Get("text")
	
	// Якщо параметр порожній, використовуємо значення за замовчуванням
	if text == "" {
		text = "Привіт! Надішліть текст у параметрі 'text', наприклад: /echo?text=ВашТекст"
	}

	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	fmt.Fprintf(w, "Ехо-відповідь (GET):\n")
	fmt.Fprintf(w, "Отриманий текст: %s\n", text)
	fmt.Fprintf(w, "Довжина тексту: %d символів\n", len(text))
}

// echoPostHandler обробляє POST запити до /echo
func echoPostHandler(w http.ResponseWriter, r *http.Request) {
	// Отримуємо тіло запиту
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Помилка читання тіла запиту", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	// Конвертуємо тіло в рядок
	text := string(body)
	
	// Якщо тіло порожнє
	if text == "" {
		text = "Надішліть текст у тілі POST запиту"
	}

	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	fmt.Fprintf(w, "Ехо-відповідь (POST):\n")
	fmt.Fprintf(w, "Отриманий текст: %s\n", text)
	fmt.Fprintf(w, "Довжина тексту: %d байт\n", len(body))
	fmt.Fprintf(w, "Метод: %s\n", r.Method)
	fmt.Fprintf(w, "Заголовок Content-Type: %s\n", r.Header.Get("Content-Type"))
}

// healthHandler обробляє шлях /health
func healthHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != "GET" {
		http.Error(w, "Метод не підтримується", http.StatusMethodNotAllowed)
		return
	}

	// Створюємо структуру для JSON відповіді
	type HealthResponse struct {
		Status    string `json:"status"`
		Timestamp string `json:"timestamp"`
		Uptime    string `json:"uptime"` // У спрощеному вигляді
	}

	// У реальному додатку тут була б логіка перевірки здоров'я
	response := HealthResponse{
		Status:    "healthy",
		Timestamp: time.Now().Format(time.RFC3339),
		Uptime:    "сервер працює",
	}

	// Конвертуємо структуру в JSON
	jsonResponse, err := json.MarshalIndent(response, "", "  ")
	if err != nil {
		http.Error(w, "Помилка формування відповіді", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Write(jsonResponse)
}

// apiInfoHandler обробляє шлях /api/info
func apiInfoHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != "GET" {
		http.Error(w, "Метод не підтримується", http.StatusMethodNotAllowed)
		return
	}

	// Створюємо структуру з інформацією про сервер
	type ServerInfo struct {
		Name        string   `json:"name"`
		Version     string   `json:"version"`
		Description string   `json:"description"`
		Endpoints   []string `json:"endpoints"`
		Host        string   `json:"host"`
		Timestamp   string   `json:"timestamp"`
	}

	info := ServerInfo{
		Name:        "Навчальний HTTP сервер",
		Version:     "1.0.0",
		Description: "Простий демонстраційний сервер для навчання Go",
		Endpoints: []string{
			"GET  /",
			"GET  /hello",
			"GET  /time",
			"GET  /echo?text=...",
			"POST /echo",
			"GET  /health",
			"GET  /api/info",
		},
		Host:      r.Host,
		Timestamp: time.Now().Format(time.RFC3339),
	}

	// Конвертуємо в JSON з відступами для читабельності
	jsonResponse, err := json.MarshalIndent(info, "", "  ")
	if err != nil {
		http.Error(w, "Помилка формування відповіді", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Write(jsonResponse)
}

// Примітки для початківців:
// 1. http.HandleFunc реєструє функцію-обробник для певного шляху
// 2. http.ResponseWriter - інтерфейс для формування HTTP відповіді
// 3. *http.Request - структура, що містить інформацію про HTTP запит
// 4. w.Header().Set() - встановлює заголовки HTTP відповіді
// 5. fmt.Fprintf(w, ...) - записує текст у тіло відповіді
// 6. http.ListenAndServe() - запускає сервер на вказаному порту
// 7. log.Fatal() - логує помилку та завершує програму, якщо сервер не може запуститися
//
// Як запустити сервер:
// 1. Збережіть файл як 15_http_server.go
// 2. Виконайте: go run 15_http_server.go
// 3. Відкрийте браузер та перейдіть за адресою: http://localhost:8080
//
// Як тестувати з командного рядка:
// curl http://localhost:8080/hello
// curl "http://localhost:8080/echo?text=Привіт"
// curl -X POST -d "message=Тест" http://localhost:8080/echo
