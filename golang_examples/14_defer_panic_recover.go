// 14_defer_panic_recover.go
// Приклади використання defer, panic та recover у Go
// Ці механізми дозволяють керувати потоком виконання та обробляти виняткові ситуації

package main

import (
	"fmt"
	"os"
)

func main() {
	fmt.Println("=== Приклади defer, panic та recover ===")
	
	// 1. defer - відкладені виклики
	// Оператор defer відкладає виконання функції до моменту повернення з поточної функції
	deferExample()
	
	// 2. panic - виклик паніки
	// Функція panic зупиняє нормальний потік виконання та починає паніку
	panicExample()
	
	// 3. recover - відновлення після паніки
	// Функція recover дозволяє відновити контроль після виклику panic
	recoverExample()
	
	// 4. Практичне використання defer
	practicalDeferExample()
}

// deferExample демонструє використання оператора defer
func deferExample() {
	fmt.Println("\n1. Приклад використання defer:")
	
	// defer викликається у зворотному порядку (LIFO - останній прийшов, перший вийшов)
	defer fmt.Println("Це буде виведено останнім (defer 3)")
	defer fmt.Println("Це буде виведено другим (defer 2)")
	defer fmt.Println("Це буде виведено першим (defer 1)")
	
	fmt.Println("Це виводиться перед всіма defer")
	
	// defer часто використовується для закриття ресурсів
	file, err := os.Create("test.txt")
	if err != nil {
		fmt.Println("Помилка створення файлу:", err)
		return
	}
	// Гарантоване закриття файлу при виході з функції
	defer file.Close()
	defer os.Remove("test.txt") // Видалення файлу після закриття
	
	// Запис у файл
	file.WriteString("Привіт, світ!\n")
	fmt.Println("Файл створено та закрито автоматично за допомогою defer")
}

// panicExample демонструє виклик паніки
func panicExample() {
	fmt.Println("\n2. Приклад використання panic:")
	
	// Звичайний виклик panic
	fmt.Println("Перед викликом panic")
	// panic("Це тестова паніка!")
	// Рядок вище закоментовано, щоб не зупиняти виконання програми
	// Розкоментуйте його, щоб побачити ефект panic
	
	// panic також викликається автоматично при певних помилках
	// Наприклад, доступ до елементу слайсу за межами його довжини
	slice := []int{1, 2, 3}
	// Це викличе panic: runtime error: index out of range [5] with length 3
	// value := slice[5]
	// fmt.Println("Це ніколи не виконається:", value)
	
	fmt.Println("Після потенційного panic (якщо panic не викликано)")
}

// recoverExample демонструє використання recover для відновлення після panic
func recoverExample() {
	fmt.Println("\n3. Приклад використання recover:")
	
	// Анонімна функція для демонстрації recover
	func() {
		defer func() {
			// recover зупиняє паніку та повертає значення, передане в panic
			if r := recover(); r != nil {
				fmt.Println("Відновлено після panic:", r)
			}
		}()
		
		fmt.Println("Перед викликом panic всередині функції")
		panic("Тестова паніка для recover")
		fmt.Println("Цей рядок ніколи не виконається")
	}()
	
	fmt.Println("Програма продовжує виконання після recover")
}

// practicalDeferExample демонструє практичне використання defer
func practicalDeferExample() {
	fmt.Println("\n4. Практичне використання defer:")
	
	// defer для вимірювання часу виконання
	defer func(startTime int64) {
		endTime := time.Now().UnixNano()
		duration := (endTime - startTime) / 1000000 // мілісекунди
		fmt.Printf("Функція виконувалася %d мс\n", duration)
	}(time.Now().UnixNano())
	
	// Імітація тривалої операції
	time.Sleep(100 * time.Millisecond)
	fmt.Println("Виконано тривалу операцію")
	
	// defer для логування
	defer fmt.Println("Завершення practicalDeferExample")
}

// Додатковий імпорт для practicalDeferExample
import "time"

// Примітка: У реальному коді імпорти мають бути об'єднані в один блок import
// Цей файл демонструє різні аспекти defer, panic та recover:
// 1. defer - для гарантованого виконання коду при виході з функції
// 2. panic - для зупинки програми при критичних помилках
// 3. recover - для обробки panic та відновлення контролю
// 4. Практичні приклади використання defer

// Для запуску цього файлу виконайте: go run 14_defer_panic_recover.go