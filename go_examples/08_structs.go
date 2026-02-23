// Приклад 08: Структури (structs) у Go
// Структури - це користувацькі типи даних, які групують поля різних типів

package main

import (
	"fmt"
)

// Оголошення структури Person з трьома полями
type Person struct {
	Name    string
	Age     int
	Country string
}

// Структура може містити інші структури
type Address struct {
	Street  string
	City    string
	ZipCode string
}

type Employee struct {
	Person  Person    // Вкладення структури
	Address Address   // Вкладення структури
	Salary  float64
}

func main() {
	// Створення екземпляра структури Person
	person1 := Person{
		Name:    "Іван",
		Age:     30,
		Country: "Україна",
	}
	fmt.Println("Структура Person:", person1)
	fmt.Println("Ім'я:", person1.Name)
	fmt.Println("Вік:", person1.Age)
	fmt.Println("Країна:", person1.Country)

	// Створення структури з нульовими значеннями
	var person2 Person
	fmt.Println("\nСтруктура з нульовими значеннями:", person2)

	// Зміна значень полів структури
	person2.Name = "Марія"
	person2.Age = 25
	person2.Country = "Польща"
	fmt.Println("Оновлена структура:", person2)

	// Створення структури з вкладеними структурами
	employee := Employee{
		Person: Person{
			Name:    "Петро",
			Age:     35,
			Country: "Україна",
		},
		Address: Address{
			Street:  "Вулиця Шевченка, 1",
			City:    "Київ",
			ZipCode: "01001",
		},
		Salary: 50000.0,
	}
	fmt.Println("\nСтруктура Employee:")
	fmt.Println("Ім'я працівника:", employee.Person.Name)
	fmt.Println("Вік:", employee.Person.Age)
	fmt.Println("Місто:", employee.Address.City)
	fmt.Println("Зарплата:", employee.Salary)

	// Анонімні структури (створюються без попереднього оголошення типу)
	car := struct {
		Brand string
		Model string
		Year  int
	}{
		Brand: "Toyota",
		Model: "Camry",
		Year:  2022,
	}
	fmt.Println("\nАнонімна структура (автомобіль):", car)

	// Порівняння структур
	person3 := Person{Name: "Іван", Age: 30, Country: "Україна"}
	person4 := Person{Name: "Іван", Age: 30, Country: "Україна"}
	person5 := Person{Name: "Марія", Age: 25, Country: "Польща"}

	fmt.Println("\nПорівняння структур:")
	fmt.Println("person3 == person4:", person3 == person4) // true
	fmt.Println("person3 == person5:", person3 == person5) // false

	// Вказівники на структури
	ptr := &person1
	fmt.Println("\nДоступ до полів через вказівник:")
	fmt.Println("Ім'я через вказівник:", ptr.Name) // Go автоматично розіменовує
	fmt.Println("Вік через вказівник:", (*ptr).Age) // Явне розіменування

	// Зміна значень через вказівник
	ptr.Age = 31
	fmt.Println("\nОновлений вік через вказівник:", person1.Age)
}