// 12_pointers.go
// Приклади роботи з вказівниками (pointers) у Go
// Вказівники дозволяють працювати з пам'яттю напряму

package main

import "fmt"

func main() {
	fmt.Println("=== Приклади вказівників у Go ===")
	
	// 1. Оголошення та ініціалізація вказівника
	fmt.Println("\n1. Оголошення та ініціалізація вказівника:")
	
	var x int = 42
	var p *int // p - вказівник на int
	p = &x    // & - оператор взяття адреси
	
	fmt.Printf("Значення x: %d\n", x)
	fmt.Printf("Адреса x: %p\n", &x)
	fmt.Printf("Значення p (адреса): %p\n", p)
	fmt.Printf("Значення за адресою p (*p): %d\n", *p)
	
	// 2. Зміна значення через вказівник
	fmt.Println("\n2. Зміна значення через вказівник:")
	
	*p = 100
	fmt.Printf("Нове значення x: %d\n", x)
	fmt.Printf("Нове значення *p: %d\n", *p)
	
	// 3. Нульовий вказівник (nil pointer)
	fmt.Println("\n3. Нульовий вказівник:")
	
	var nilPtr *int
	fmt.Printf("nilPtr = %p\n", nilPtr)
	
	// Спроба розіменувати nil вказівник призведе до panic
	// fmt.Println(*nilPtr) // Це викличе panic!
	
	// Перевірка на nil перед розіменуванням
	if nilPtr == nil {
		fmt.Println("nilPtr є нульовим вказівником, не можна розіменувати")
	}
	
	// 4. Вказівники на різні типи
	fmt.Println("\n4. Вказівники на різні типи:")
	
	var str string = "Hello"
	var strPtr *string = &str
	
	fmt.Printf("str: %s\n", str)
	fmt.Printf("*strPtr: %s\n", *strPtr)
	
	// 5. Вказівники на структури
	fmt.Println("\n5. Вказівники на структури:")
	
	type Person struct {
		Name string
		Age  int
	}
	
	person := Person{"Іван", 30}
	personPtr := &person
	
	// Доступ до полів структури через вказівник
	fmt.Printf("person.Name: %s\n", person.Name)
	fmt.Printf("personPtr.Name: %s\n", personPtr.Name) // Go автоматично розіменовує
	fmt.Printf("(*personPtr).Name: %s\n", (*personPtr).Name) // Явне розіменування
	
	// Зміна поля через вказівник
	personPtr.Age = 31
	fmt.Printf("Новий вік: %d\n", person.Age)
	
	// 6. Вказівники в функціях (передача за посиланням)
	fmt.Println("\n6. Вказівники в функціях:")
	
	a, b := 10, 20
	fmt.Printf("До swap: a=%d, b=%d\n", a, b)
	swap(&a, &b)
	fmt.Printf("Після swap: a=%d, b=%d\n", a, b)
	
	// 7. Вказівники на масиви
	fmt.Println("\n7. Вказівники на масиви:")
	
	arr := [3]int{1, 2, 3}
	arrPtr := &arr
	
	fmt.Printf("arr: %v\n", arr)
	fmt.Printf("arrPtr: %v\n", *arrPtr)
	
	// Зміна елемента масиву через вказівник
	arrPtr[0] = 100
	fmt.Printf("Змінений arr: %v\n", arr)
	
	// 8. new() - створення вказівника на нову змінну
	fmt.Println("\n8. Використання new():")
	
	ptr := new(int) // new повертає вказівник на новий int з нульовим значенням
	*ptr = 77
	fmt.Printf("Значення за ptr: %d\n", *ptr)
	
	// 9. Вказівники на вказівники
	fmt.Println("\n9. Вказівники на вказівники:")
	
	value := 5
	p1 := &value
	p2 := &p1
	
	fmt.Printf("value: %d\n", value)
	fmt.Printf("*p1: %d\n", *p1)
	fmt.Printf("**p2: %d\n", **p2)
	
	// 10. Практичне застосування: ефективність
	fmt.Println("\n10. Практичне застосування:")
	fmt.Println("Вказівники дозволяють:")
	fmt.Println("  - Ефективно передавати великі структури в функції")
	fmt.Println("  - Змінювати значення змінних у функціях")
	fmt.Println("  - Працювати з динамічною пам'яттю")
	fmt.Println("  - Створювати зв'язані структури даних")
}

// Функція для обміну значень через вказівники
func swap(x, y *int) {
	// Типовий алгоритм обміну з використанням тимчасової змінної
	temp := *x
	*x = *y
	*y = temp
}
