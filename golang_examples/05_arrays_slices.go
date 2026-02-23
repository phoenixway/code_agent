// Файл: 05_arrays_slices.go
// Приклади роботи з масивами та зрізами (slices) у Go
// Зрізи - це динамічні представлення масивів, більш гнучкі та поширені

package main

import "fmt"

func main() {
	fmt.Println("=== Масиви та зрізи в Go ===")

	// 1. Масиви - фіксованого розміру
	// Оголошення масиву з 3 цілих чисел
	var arr1 [3]int
	arr1[0] = 10
	arr1[1] = 20
	arr1[2] = 30
	fmt.Printf("Масив arr1: %v\n", arr1)
	fmt.Printf("Довжина масиву arr1: %d\n", len(arr1))

	// Ініціалізація масиву при оголошенні
	arr2 := [3]string{"Яблуко", "Банан", "Апельсин"}
	fmt.Printf("Масив arr2: %v\n", arr2)

	// Масив з автоматичним визначенням розміру
	arr3 := [...]int{1, 2, 3, 4, 5}
	fmt.Printf("Масив arr3 (авто-розмір): %v, довжина: %d\n", arr3, len(arr3))

	// 2. Зрізи (slices) - динамічні
	// Створення зрізу
	var slice1 []int // порожній зріз
	fmt.Printf("Зріз slice1: %v, довжина: %d, ємність: %d\n", slice1, len(slice1), cap(slice1))

	// Ініціалізація зрізу з значеннями
	slice2 := []int{10, 20, 30, 40, 50}
	fmt.Printf("Зріз slice2: %v, довжина: %d\n", slice2, len(slice2))

	// Створення зрізу з допомогою make
	slice3 := make([]int, 3) // зріз з 3 елементів (значення 0)
	slice3[0] = 100
	slice3[1] = 200
	slice3[2] = 300
	fmt.Printf("Зріз slice3 (make): %v\n", slice3)

	// Зріз з певною початковою ємністю
	slice4 := make([]int, 0, 5) // довжина 0, ємність 5
	fmt.Printf("Зріз slice4: довжина=%d, ємність=%d\n", len(slice4), cap(slice4))

	// 3. Операції зі зрізами
	// Додавання елементів (append)
	slice5 := []int{1, 2, 3}
	slice5 = append(slice5, 4, 5, 6)
	fmt.Printf("Після append: %v\n", slice5)

	// Додавання одного зрізу до іншого
	slice6 := []int{10, 20}
	slice7 := []int{30, 40, 50}
	slice6 = append(slice6, slice7...) // ... розпаковує зріз
	fmt.Printf("Об'єднання зрізів: %v\n", slice6)

	// Вирізання частини зрізу (slicing)
	original := []int{0, 1, 2, 3, 4, 5, 6, 7, 8, 9}
	part1 := original[2:5] // елементи з індексами 2, 3, 4
	fmt.Printf("Виріз original[2:5]: %v\n", part1)

	part2 := original[:3] // перші 3 елементи
	fmt.Printf("Виріз original[:3]: %v\n", part2)

	part3 := original[7:] // з 7-го до кінця
	fmt.Printf("Виріз original[7:]: %v\n", part3)

	// Копіювання зрізів
	source := []int{1, 2, 3, 4, 5}
	destination := make([]int, 3)
	copy(destination, source) // копіює перші 3 елементи
	fmt.Printf("Копія: source=%v, destination=%v\n", source, destination)

	// 4. Двовимірні зрізи
	matrix := [][]int{
		{1, 2, 3},
		{4, 5, 6},
		{7, 8, 9},
	}
	fmt.Println("Двовимірний зріз (матриця):")
	for i, row := range matrix {
		fmt.Printf("  Рядок %d: %v\n", i, row)
	}

	// 5. Порівняння масивів та зрізів
	// Масиви можна порівнювати оператором ==
	arrA := [2]int{1, 2}
	arrB := [2]int{1, 2}
	arrC := [2]int{1, 3}
	fmt.Printf("arrA == arrB: %v\n", arrA == arrB) // true
	fmt.Printf("arrA == arrC: %v\n", arrA == arrC) // false

	// Зрізи не можна порівнювати оператором ==
	// Для порівняння зрізів потрібно використовувати reflect.DeepEqual або писати власну функцію

	fmt.Println("\n=== Ключові відмінності ===")
	fmt.Println("1. Масиви: фіксований розмір, значення передаються за значенням (копіювання)")
	fmt.Println("2. Зрізи: динамічний розмір, передаються за посиланням (не копіюються)")
	fmt.Println("3. Зрізи частіше використовуються на практиці через гнучкість")
}
