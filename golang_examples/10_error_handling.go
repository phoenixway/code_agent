// 10_error_handling.go
// Обробка помилок у Go

package main

import (
	"errors"
	"fmt"
	"os"
	"strconv"
)

func main() {
	fmt.Println("=== Обробка помилок у Go ===")
	
	// 1. Базовий приклад обробки помилок
	fmt.Println("\n1. Базовий приклад обробки помилок:")
	
	// Функція, яка повертає помилку
	result, err := divide(10, 2)
	if err != nil {
		fmt.Printf("Помилка: %v\n", err)
	} else {
		fmt.Printf("Результат: %v\n", result)
	}
	
	// Спроба поділити на 0
	result, err = divide(10, 0)
	if err != nil {
		fmt.Printf("Помилка: %v\n", err)
	} else {
		fmt.Printf("Результат: %v\n", result)
	}
	
	// 2. Створення власних помилок
	fmt.Println("\n2. Створення власних помилок:")
	
	age, err := validateAge(15)
	if err != nil {
		fmt.Printf("Помилка: %v\n", err)
	} else {
		fmt.Printf("Вік: %d\n", age)
	}
	
	age, err = validateAge(-5)
	if err != nil {
		fmt.Printf("Помилка: %v\n", err)
	} else {
		fmt.Printf("Вік: %d\n", age)
	}
	
	// 3. errors.New та fmt.Errorf
	fmt.Println("\n3. errors.New та fmt.Errorf:")
	
	err1 := errors.New("це проста помилка")
	fmt.Printf("Помилка 1: %v\n", err1)
	
	err2 := fmt.Errorf("це помилка з форматуванням: %s", "невірний формат")
	fmt.Printf("Помилка 2: %v\n", err2)
	
	// 4. Перевірка типів помилок
	fmt.Println("\n4. Перевірка типів помилок:")
	
	filePath := "неіснуючий_файл.txt"
	content, err := readFile(filePath)
	if err != nil {
		// Перевірка, чи це помилка "файл не знайдено"
		if os.IsNotExist(err) {
			fmt.Printf("Файл %s не існує\n", filePath)
		} else {
			fmt.Printf("Інша помилка: %v\n", err)
		}
	} else {
		fmt.Printf("Вміст файлу: %s\n", content)
	}
	
	// 5. Паніка (panic) та відновлення (recover)
	fmt.Println("\n5. Паніка (panic) та відновлення (recover):")
	
	safeDivide(10, 2)
	safeDivide(10, 0) // Викличе паніку, але ми її перехопимо
	
	fmt.Println("\nПрограма завершилася успішно!")
}

// Функція ділення, яка повертає помилку при діленні на 0
func divide(a, b float64) (float64, error) {
	if b == 0 {
		return 0, errors.New("ділення на нуль")
	}
	return a / b, nil
}

// Функція перевірки віку
func validateAge(age int) (int, error) {
	if age < 0 {
		return 0, errors.New("вік не може бути від'ємним")
	}
	if age < 18 {
		return age, fmt.Errorf("вік %d занадто малий", age)
	}
	return age, nil
}

// Функція читання файлу
func readFile(filename string) (string, error) {
	// Спроба відкрити файл
	file, err := os.Open(filename)
	if err != nil {
		return "", err // Повертаємо помилку як є
	}
	defer file.Close()
	
	// Читаємо вміст (спрощений приклад)
	content := "Вміст файлу " + filename
	return content, nil
}

// Безпечне ділення з перехопленням паніки
func safeDivide(a, b float64) {
	defer func() {
		if r := recover(); r != nil {
			fmt.Printf("Перехоплено паніку: %v\n", r)
			fmt.Println("Продовжуємо виконання програми...")
		}
	}()
	
	if b == 0 {
		panic("ділення на нуль у safeDivide")
	}
	
	result := a / b
	fmt.Printf("Результат safeDivide: %v\n", result)
}

// 6. Множинні помилки
func processData(data string) error {
	if data == "" {
		return errors.New("дані порожні")
	}
	
	// Спроба конвертувати в число
	_, err := strconv.Atoi(data)
	if err != nil {
		return fmt.Errorf("неможливо конвертувати '%s' в число: %v", data, err)
	}
	
	return nil
}