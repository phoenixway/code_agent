// Файл: 06_maps.go
// Приклади роботи з мапами (словниками) у Go
// Мапа - це колекція пар ключ-значення

package main

import "fmt"

func main() {
	fmt.Println("=== Приклади роботи з мапами (maps) ===")

	// 1. Створення мапи
	// Синтаксис: map[тип_ключа]тип_значення
	var capitals map[string]string // оголошення мапи (поки nil)
	fmt.Printf("Мапа capitals після оголошення: %v (nil? %v)\n", capitals, capitals == nil)

	// 2. Ініціалізація мапи за допомогою make
	capitals = make(map[string]string)
	fmt.Printf("Мапа capitals після make: %v\n", capitals)

	// 3. Додавання елементів до мапи
	capitals["Україна"] = "Київ"
	capitals["Польща"] = "Варшава"
	capitals["Німеччина"] = "Берлін"
	fmt.Printf("Мапа capitals після додавання: %v\n", capitals)

	// 4. Отримання значення за ключем
	ukraineCapital := capitals["Україна"]
	fmt.Printf("Столиця України: %s\n", ukraineCapital)

	// 5. Перевірка наявності ключа в мапі
	// При отриманні значення можна отримати другий параметр - булеве значення, яке вказує, чи існує ключ
	capital, exists := capitals["Франція"]
	if exists {
		fmt.Printf("Столиця Франції: %s\n", capital)
	} else {
		fmt.Println("Ключ 'Франція' не знайдено в мапі")
	}

	// 6. Видалення елемента з мапи
	delete(capitals, "Польща")
	fmt.Printf("Мапа capitals після видалення 'Польща': %v\n", capitals)

	// 7. Ітерація по мапі за допомогою range
	fmt.Println("\nІтерація по мапі capitals:")
	for country, capital := range capitals {
		fmt.Printf("  %s -> %s\n", country, capital)
	}

	// 8. Створення та ініціалізація мапи одразу
	ages := map[string]int{
		"Анна":   25,
		"Богдан": 30,
		"Олена":  28,
	}
	fmt.Printf("\nМапа ages: %v\n", ages)

	// 9. Довжина мапи (кількість елементів)
	fmt.Printf("Кількість елементів у мапі ages: %d\n", len(ages))

	// 10. Мапа зі складнішими типами
	// Мапа, де значення - це масив чисел
	studentGrades := map[string][3]int{
		"Іван":   {85, 90, 78},
		"Марія":  {92, 88, 95},
		"Петро":  {76, 82, 80},
	}
	fmt.Println("\nОцінки студентів:")
	for student, grades := range studentGrades {
		fmt.Printf("  %s: %v\n", student, grades)
	}

	// 11. Вкладені мапи
	employees := map[string]map[string]string{
		"john": {
			"position": "developer",
			"department": "IT",
		},
		"jane": {
			"position": "manager",
			"department": "HR",
		},
	}
	fmt.Println("\nІнформація про співробітників:")
	for id, info := range employees {
		fmt.Printf("  %s: посада=%s, відділ=%s\n", id, info["position"], info["department"])
	}

	// 12. Очищення мапи
	// Щоб очистити мапу, можна пройтись по всіх ключах і видалити їх,
	// або просто створити нову мапу
	tempMap := map[string]int{"a": 1, "b": 2, "c": 3}
	fmt.Printf("\nМапа tempMap до очищення: %v\n", tempMap)
	// Спосіб 1: створити нову мапу
	tempMap = make(map[string]int)
	fmt.Printf("Мапа tempMap після очищення (make): %v\n", tempMap)

	// Спосіб 2: видалити всі елементи
	tempMap = map[string]int{"x": 10, "y": 20, "z": 30}
	for key := range tempMap {
		delete(tempMap, key)
	}
	fmt.Printf("Мапа tempMap після видалення всіх елементів: %v\n", tempMap)

	fmt.Println("\n=== Кінець прикладів з мапами ===")
}