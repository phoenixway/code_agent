// Приклад 05: Умовні оператори та цикли

package main

import "fmt"

func main() {
	fmt.Println("=== Умовні оператори ===")
	
	// 1. Простий if
	age := 18
	if age >= 18 {
		fmt.Println("Ви повнолітній")
	}
	
	// 2. if-else
	temperature := 25
	if temperature > 30 {
		fmt.Println("Спекотно")
	} else if temperature > 20 {
		fmt.Println("Тепло")
	} else {
		fmt.Println("Прохолодно")
	}
	
	// 3. if з коротким виразом (short statement)
	// Можна оголосити змінну прямо в умові
	if num := 10; num%2 == 0 {
		fmt.Println(num, "- парне число")
	}
	
	fmt.Println("\n=== Цикли ===")
	
	// 4. Цикл for (класичний)
	fmt.Println("Цикл for (класичний):")
	for i := 0; i < 5; i++ {
		fmt.Printf("i = %d\n", i)
	}
	
	// 5. Цикл for (як while)
	fmt.Println("\nЦикл for (як while):")
	j := 0
	for j < 3 {
		fmt.Printf("j = %d\n", j)
		j++
	}
	
	// 6. Безкінечний цикл
	fmt.Println("\nБезкінечний цикл (з break):")
	counter := 0
	for {
		if counter >= 3 {
			break // вихід з циклу
		}
		fmt.Printf("counter = %d\n", counter)
		counter++
	}
	
	// 7. Цикл for range (для масивів, зрізів, рядків, мап)
	fmt.Println("\nЦикл for range:")
	fruits := []string{"яблуко", "банан", "апельсин"}
	for index, fruit := range fruits {
		fmt.Printf("Індекс: %d, Фрукт: %s\n", index, fruit)
	}
	
	// 8. Оператор continue
	fmt.Println("\nОператор continue (пропускаємо парні числа):")
	for i := 0; i < 10; i++ {
		if i%2 == 0 {
			continue // переходимо до наступної ітерації
		}
		fmt.Printf("%d ", i)
	}
	fmt.Println()
	
	// 9. Switch statement
	fmt.Println("\n=== Оператор switch ===")
	day := "понеділок"
	
	switch day {
	case "понеділок":
		fmt.Println("Початок тижня")
	case "вівторок", "середа", "четвер":
		fmt.Println("Середина тижня")
	case "п'ятниця":
		fmt.Println("Кінець робочого тижня")
	case "субота", "неділя":
		fmt.Println("Вихідні")
	default:
		fmt.Println("Невідомий день")
	}
	
	// 10. Switch без виразу (як if-else ланцюжок)
	hour := 14
	switch {
	case hour < 12:
		fmt.Println("Доброго ранку!")
	case hour < 18:
		fmt.Println("Доброго дня!")
	default:
		fmt.Println("Доброго вечора!")
	}
}
