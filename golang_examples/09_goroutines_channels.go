// Файл: 09_goroutines_channels.go
// Приклади горутин та каналів у Go
// Горутини - це легковісні потоки виконання, а канали - це спосіб спілкування між горутинами

package main

import (
	"fmt"
	"time"
)

func main() {
	fmt.Println("=== Приклади горутин та каналів ===")
	
	// 1. Проста горутина
	fmt.Println("\n1. Проста горутина:")
	go sayHello() // Запускаємо функцію в окремій горутині
	time.Sleep(100 * time.Millisecond) // Чекаємо, щоб горутина встигла виконатись
	
	// 2. Горутина з анонімною функцією
	fmt.Println("\n2. Горутина з анонімною функцією:")
	go func() {
		fmt.Println("Анонімна функція виконується в горутині")
	}()
	time.Sleep(100 * time.Millisecond)
	
	// 3. Канали для спілкування між горутинами
	fmt.Println("\n3. Канали для спілкування:")
	messages := make(chan string) // Створюємо канал для рядків
	
	// Запускаємо горутину, яка надсилає повідомлення в канал
	go func() {
		messages <- "Привіт з горутини!"
	}()
	
	// Отримуємо повідомлення з каналу
	msg := <-messages
	fmt.Println("Отримано:", msg)
	
	// 4. Буферизовані канали
	fmt.Println("\n4. Буферизовані канали:")
	buffered := make(chan string, 2) // Канал з буфером на 2 елементи
	buffered <- "Перше повідомлення"
	buffered <- "Друге повідомлення"
	// buffered <- "Третє повідомлення" // Це заблокувало б програму, бо буфер заповнений
	
	fmt.Println("Отримано з буфера:", <-buffered)
	fmt.Println("Отримано з буфера:", <-buffered)
	
	// 5. Синхронізація горутин
	fmt.Println("\n5. Синхронізація горутин:")
	done := make(chan bool)
	
	go worker(done)
	
	// Чекаємо на сигнал від горутини
	<-done
	fmt.Println("Роботу завершено!")
	
	// 6. Вибір з кількох каналів (select)
	fmt.Println("\n6. Вибір з кількох каналів (select):")
	c1 := make(chan string)
	c2 := make(chan string)
	
	go func() {
		time.Sleep(1 * time.Second)
		c1 <- "один"
	}()
	
	go func() {
		time.Sleep(2 * time.Second)
		c2 <- "два"
	}()
	
	for i := 0; i < 2; i++ {
		select {
		case msg1 := <-c1:
			fmt.Println("Отримано:", msg1)
		case msg2 := <-c2:
			fmt.Println("Отримано:", msg2)
		}
	}
	
	// 7. Закриття каналів
	fmt.Println("\n7. Закриття каналів:")
	jobs := make(chan int, 5)
	doneChan := make(chan bool)
	
	// Робоча горутина
	go func() {
		for {
			j, more := <-jobs
			if more {
				fmt.Println("Отримано роботу:", j)
			} else {
				fmt.Println("Усі роботи отримано")
				doneChan <- true
				return
			}
		}
	}()
	
	// Надсилаємо роботи
	for j := 1; j <= 3; j++ {
		jobs <- j
		fmt.Println("Надіслано роботу:", j)
		time.Sleep(100 * time.Millisecond)
	}
	close(jobs) // Закриваємо канал
	fmt.Println("Надіслано всі роботи")
	
	// Чекаємо на завершення робочої горутини
	<-doneChan
	
	fmt.Println("\n=== Кінець прикладів горутин та каналів ===")
}

// Допоміжні функції

func sayHello() {
	fmt.Println("Привіт з горутини!")
}

func worker(done chan bool) {
	fmt.Print("Робота виконується...")
	time.Sleep(500 * time.Millisecond)
	fmt.Println(" готово!")
	done <- true
}
