// Файл: 07_structs.go
// Приклади структур (structs) у Go
// Структури - це користувацькі типи даних, які групують поля різних типів

package main

import (
	"fmt"
)

// Оголошення простої структури
type Person struct {
	Name    string
	Age     int
	Country string
}

// Структура з вкладеними полями
type Address struct {
	City    string
	Street  string
	ZipCode string
}

type Employee struct {
	ID      int
	Person  Person    // Вкладена структура
	Address Address   // Вкладена структура
	Salary  float64
}

// Методи для структур (функції з отримувачем)
// Метод з отримувачем за значенням
func (p Person) Greet() string {
	return fmt.Sprintf("Привіт, мене звати %s, мені %d років з %s", p.Name, p.Age, p.Country)
}

// Метод з отримувачем за вказівником (може змінювати структуру)
func (p *Person) HaveBirthday() {
	p.Age++
	fmt.Printf("%s відсвяткував(ла) день народження! Тепер йому/їй %d років\n", p.Name, p.Age)
}

// Метод для структури Employee
func (e Employee) GetInfo() string {
	return fmt.Sprintf("Працівник #%d: %s, зарплата: %.2f, місто: %s", 
		e.ID, e.Person.Name, e.Salary, e.Address.City)
}

func main() {
	fmt.Println("=== Приклади структур (structs) у Go ===")
	fmt.Println()

	// 1. Створення структури та ініціалізація
	fmt.Println("1. Створення та ініціалізація структур:")
	
	// Способи створення структури
	var person1 Person // Всі поля отримають нульові значення
	person1.Name = "Іван"
	person1.Age = 30
	person1.Country = "Україна"
	fmt.Printf("  person1: %+v\n", person1)
	
	// Літерал структури (найпоширеніший спосіб)
	person2 := Person{
		Name:    "Марія",
		Age:     25,
		Country: "Польща",
	}
	fmt.Printf("  person2: %+v\n", person2)
	
	// Скорочений запис (порядок полів важливий)
	person3 := Person{"Петро", 35, "Німеччина"}
	fmt.Printf("  person3: %+v\n", person3)
	
	// 2. Доступ до полів структури
	fmt.Println("\n2. Доступ до полів структури:")
	fmt.Printf("  Ім'я person2: %s\n", person2.Name)
	fmt.Printf("  Вік person3: %d\n", person3.Age)
	
	// Зміна значення поля
	person2.Age = 26
	fmt.Printf("  Оновлений вік person2: %d\n", person2.Age)
	
	// 3. Вкладені структури
	fmt.Println("\n3. Вкладені структури:")
	
	employee1 := Employee{
		ID: 1001,
		Person: Person{
			Name:    "Олександр",
			Age:     40,
			Country: "Україна",
		},
		Address: Address{
			City:    "Київ",
			Street:  "Хрещатик",
			ZipCode: "01001",
		},
		Salary: 50000.50,
	}
	fmt.Printf("  employee1: %+v\n", employee1)
	fmt.Printf("  Місто працівника: %s\n", employee1.Address.City)
	fmt.Printf("  Країна працівника: %s\n", employee1.Person.Country)
	
	// 4. Методи структур
	fmt.Println("\n4. Методи структур:")
	
	// Виклик методу з отримувачем за значенням
	greeting := person2.Greet()
	fmt.Printf("  %s\n", greeting)
	
	// Виклик методу з отримувачем за вказівником
	fmt.Printf("  Вік до дня народження: %d\n", person2.Age)
	person2.HaveBirthday()
	fmt.Printf("  Вік після дня народження: %d\n", person2.Age)
	
	// Метод для Employee
	empInfo := employee1.GetInfo()
	fmt.Printf("  %s\n", empInfo)
	
	// 5. Порівняння структур
	fmt.Println("\n5. Порівняння структур:")
	
	person4 := Person{"Іван", 30, "Україна"}
	person5 := Person{"Іван", 30, "Україна"}
	person6 := Person{"Іван", 31, "Україна"}
	
	fmt.Printf("  person4 == person5: %v (очікується true)\n", person4 == person5)
	fmt.Printf("  person4 == person6: %v (очікується false)\n", person4 == person6)
	
	// 6. Анонімні структури
	fmt.Println("\n6. Анонімні структури:")
	
	// Створення анонімної структури без оголошення типу
	car := struct {
		Brand string
		Model string
		Year  int
	}{
		Brand: "Toyota",
		Model: "Camry",
		Year:  2020,
	}
	fmt.Printf("  Анонімна структура (авто): %+v\n", car)
	
	// 7. Вказівники на структури
	fmt.Println("\n7. Вказівники на структури:")
	
	ptr := &person3
	fmt.Printf("  person3 через вказівник: %+v\n", *ptr)
	fmt.Printf("  Ім'я через вказівник: %s\n", ptr.Name) // Go автоматично розіменовує
	
	// Зміна через вказівник
	ptr.Age = 36
	fmt.Printf("  Оновлений вік person3: %d\n", person3.Age)
	
	fmt.Println("\n=== Кінець прикладів структур ===")
}
