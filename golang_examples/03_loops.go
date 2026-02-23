// Файл: 03_loops.go
// Приклади циклів у мові Go
// Цикл for - єдиний тип циклу у Go, але може використовуватися різними способами

package main

import "fmt"

func main() {
	fmt.Println("=== Приклади циклів у Go ===")

	// 1. Класичний цикл for з лічильником (аналог for i=0; i<10; i++)
	fmt.Println("\n1. Класичний цикл for:")
	for i := 0; i < 5; i++ {
		fmt.Printf("i = %d\n", i)
	}

	// 2. Цикл while-стиль (тільки умова)
	fmt.Println("\n2. Цикл while-стиль (тільки умова):")
	j := 0
	for j < 3 {
		fmt.Printf("j = %d\n", j)
		j++
	}

	// 3. Вічний цикл (break для виходу)
	fmt.Println("\n3. Вічний цикл (з break):")
	count := 0
	for {
		if count >= 3 {
			break // вихід з циклу
		}
		fmt.Printf("count = %d\n", count)
		count++
	}

	// 4. Цикл for range для масивів/зрізів
	fmt.Println("\n4. Цикл for range для зрізів:")
	fruits := []string{"яблуко", "банан", "апельсин"}
	for index, fruit := range fruits {
		fmt.Printf("Індекс: %d, Фрукт: %s\n", index, fruit)
	}

	// 5. Цикл for range тільки для значень (ігноруємо індекс)
	fmt.Println("\n5. Цикл for range (тільки значення):")
	for _, fruit := range fruits {
		fmt.Printf("Фрукт: %s\n", fruit)
	}

	// 6. Цикл for range для мап
	fmt.Println("\n6. Цикл for range для мап:")
	ages := map[string]int{
		"Анна":   25,
		"Богдан": 30,
		"Олена":  28,
	}
	for name, age := range ages {
		fmt.Printf("%s: %d років\n", name, age)
	}

	// 7. Використання continue для пропуску ітерації
	fmt.Println("\n7. Використання continue:")
	for i := 0; i < 10; i++ {
		if i%2 == 0 { // пропускаємо парні числа
			continue
		}
		fmt.Printf("Непарне число: %d\n", i)
	}

	// 8. Вкладений цикл
	fmt.Println("\n8. Вкладений цикл (таблиця множення):")
	for i := 1; i <= 3; i++ {
		for j := 1; j <= 3; j++ {
			fmt.Printf("%d * %d = %d\t", i, j, i*j)
		}
		fmt.Println()
	}

	// 9. Цикл з міткою (label) для break/continue
	fmt.Println("\n9. Цикл з міткою (label):")
	outerLoop:
	for i := 0; i < 3; i++ {
		for j := 0; j < 3; j++ {
			if i == 1 && j == 1 {
				fmt.Println("Перериваємо зовнішній цикл при i=1, j=1")
				break outerLoop
			}
			fmt.Printf("i=%d, j=%d\n", i, j)
		}
	}

	fmt.Println("\n=== Кінець прикладів циклів ===")
}
