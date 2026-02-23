// Приклад 06: Масиви та зрізи (arrays and slices)
// Зрізи - це динамічні масиви в Go, які є більш гнучкими, ніж фіксовані масиви

package main

import "fmt"

func main() {
	// 1. Масиви (arrays) - фіксованого розміру
	// Синтаксис: [розмір]тип{значення}
	var arr1 [3]int = [3]int{1, 2, 3}
	fmt.Println("Масив arr1:", arr1)
	
	// Короткий запис масиву
	arr2 := [4]string{"яблуко", "банан", "апельсин", "виноград"}
	fmt.Println("Масив arr2:", arr2)
	
	// Доступ до елементів масиву (індексація з 0)
	fmt.Println("Перший елемент arr2:", arr2[0])
	fmt.Println("Другий елемент arr2:", arr2[1])
	
	// Зміна елемента масиву
	arr2[2] = "лимон"
	fmt.Println("arr2 після зміни:", arr2)
	
	// Довжина масиву
	fmt.Println("Довжина arr2:", len(arr2))
	
	// 2. Зрізи (slices) - динамічні масиви
	// Створення зрізу з використанням make
	slice1 := make([]int, 3) // зріз з 3 елементів, ініціалізованих нулями
	slice1[0] = 10
	slice1[1] = 20
	slice1[2] = 30
	fmt.Println("Зріз slice1:", slice1)
	
	// Створення зрізу з літералом
	slice2 := []string{"червоний", "зелений", "синій"}
	fmt.Println("Зріз slice2:", slice2)
	
	// Додавання елементів до зрізу (append)
	slice2 = append(slice2, "жовтий")
	slice2 = append(slice2, "фіолетовий", "помаранчевий")
	fmt.Println("slice2 після додавання:", slice2)
	
	// Зріз зрізу (slice slicing)
	// Синтаксис: slice[початок:кінець]
	// Початок включно, кінець не включно
	subSlice := slice2[1:4]
	fmt.Println("Підзріз slice2[1:4]:", subSlice)
	
	// Зріз з пропущеними індексами
	fmt.Println("slice2[:3] (перші 3 елементи):", slice2[:3])
	fmt.Println("slice2[2:] (з 3-го до кінця):", slice2[2:])
	fmt.Println("slice2[:] (весь зріз):", slice2[:])
	
	// Копіювання зрізів
	slice3 := make([]string, len(slice2))
	copy(slice3, slice2)
	fmt.Println("Копія slice2 (slice3):", slice3)
	
	// 3. Двовимірні зрізи
	matrix := [][]int{
		{1, 2, 3},
		{4, 5, 6},
		{7, 8, 9},
	}
	fmt.Println("Двовимірний зріз (матриця):")
	for i := 0; i < len(matrix); i++ {
		fmt.Println(matrix[i])
	}
	
	// 4. Практичний приклад: фільтрація чисел
	numbers := []int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
	var evenNumbers []int
	
	for _, num := range numbers {
		if num%2 == 0 {
			evenNumbers = append(evenNumbers, num)
		}
	}
	fmt.Println("Парні числа:", evenNumbers)
}
