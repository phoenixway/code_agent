// Файл: 02_conditionals.go
// Умовні оператори в Go: if, else if, else, switch

package main

import (
	"fmt"
)

func main() {
	// 1. Простий оператор if
	age := 18
	if age >= 18 {
		fmt.Println("Ви повнолітній")
	}

	// 2. If з else
	temperature := 25.5
	if temperature > 30 {
		fmt.Println("Дуже жарко")
	} else {
		fmt.Println("Температура нормальна")
	}

	// 3. If з else if та else
	score := 85
	if score >= 90 {
		fmt.Println("Оцінка: A")
	} else if score >= 80 {
		fmt.Println("Оцінка: B")
	} else if score >= 70 {
		fmt.Println("Оцінка: C")
	} else {
		fmt.Println("Оцінка: D або нижче")
	}

	// 4. Короткий запис if з оголошенням змінної
	// Змінна, оголошена в умові, видима тільки в блоках if/else
	if x := 10; x > 5 {
		fmt.Println("x більше 5")
	} else {
		fmt.Println("x менше або дорівнює 5")
	}

	// 5. Оператор switch (простий варіант)
	day := 3
	switch day {
	case 1:
		fmt.Println("Понеділок")
	case 2:
		fmt.Println("Вівторок")
	case 3:
		fmt.Println("Середа")
	case 4:
		fmt.Println("Четвер")
	case 5:
		fmt.Println("П'ятниця")
	case 6:
		fmt.Println("Субота")
	case 7:
		fmt.Println("Неділя")
	default:
		fmt.Println("Невірний день")
	}

	// 6. Switch без виразу (аналог if-else ланцюжка)
	hour := 14
	switch {
	case hour < 12:
		fmt.Println("Доброго ранку!")
	case hour < 18:
		fmt.Println("Доброго дня!")
	default:
		fmt.Println("Доброго вечора!")
	}

	// 7. Switch з декількома значеннями в case
	month := "січень"
	switch month {
	case "грудень", "січень", "лютий":
		fmt.Println("Зима")
	case "березень", "квітень", "травень":
		fmt.Println("Весна")
	case "червень", "липень", "серпень":
		fmt.Println("Літо")
	case "вересень", "жовтень", "листопад":
		fmt.Println("Осінь")
	default:
		fmt.Println("Невідомий місяць")
	}

	// 8. Switch з fallthrough (продовження виконання наступного case)
	num := 2
	switch num {
	case 1:
		fmt.Println("Один")
	case 2:
		fmt.Println("Два")
		fallthrough // Виконається і наступний case
	case 3:
		fmt.Println("Три (або fallthrough з 2)")
	case 4:
		fmt.Println("Чотири")
	}
}
