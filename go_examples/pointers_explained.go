// pointers_explained.go
// Файл демонструє роботу з вказівниками у мові Go
// Вказівники - це змінні, які зберігають адресу пам'яті іншої змінної
package main

import "fmt"

func main() {
    // 1. ОСНОВИ ВКАЗІВНИКІВ
    // Оператор & (амперсанд) повертає адресу змінної
    // Оператор * (зірочка) використовується для:
    //   - оголошення змінної-вказівника
    //   - розіменування вказівника (отримання значення за адресою)
    
    var x int = 42
    fmt.Printf("Змінна x: значення=%d, адреса=%p\n", x, &x)
    
    // Створення вказівника на x
    var p *int = &x
    fmt.Printf("Вказівник p: значення (адреса)=%p, розіменоване значення=%d\n", p, *p)
    
    // 2. ЗМІНА ЗНАЧЕННЯ ЧЕРЕЗ ВКАЗІВНИК
    // Змінюючи значення через вказівник, ми змінюємо оригінальну змінну
    *p = 100
    fmt.Printf("Після зміни через вказівник: x=%d, *p=%d\n", x, *p)
    
    // 3. ВКАЗІВНИКИ НА СТРУКТУРИ
    type Person struct {
        Name string
        Age  int
    }
    
    person1 := Person{Name: "Іван", Age: 30}
    personPtr := &person1
    
    // Доступ до полів структури через вказівник:
    // Способи 1: (*personPtr).Name
    // Способи 2: personPtr.Name (Go автоматично розіменовує)
    fmt.Printf("Особа: %s, %d років\n", (*personPtr).Name, personPtr.Age)
    
    // 4. ВКАЗІВНИКИ ЯК ПАРАМЕТРИ ФУНКЦІЙ
    // Функція, яка приймає вказівник, може змінювати оригінальне значення
    increment := func(n *int) {
        *n += 1
    }
    
    counter := 5
    fmt.Printf("До виклику increment: counter=%d\n", counter)
    increment(&counter)
    fmt.Printf("Після виклику increment: counter=%d\n", counter)
    
    // 5. НІЛЬНІ ВКАЗІВНИКИ
    // Вказівник, який не вказує на жодну змінну, має значення nil
    var nilPtr *int
    fmt.Printf("Нільний вказівник: %v\n", nilPtr)
    
    // Спроба розіменувати нільний вказівник викличе panic
    // *nilPtr = 5 // Це викличе panic: runtime error: invalid memory address
    
    // Безпечна перевірка на nil перед розіменуванням
    if nilPtr != nil {
        fmt.Println("Вказівник не nil, можна розіменувати")
    } else {
        fmt.Println("Вказівник nil, небезпечно розіменовувати")
    }
    
    // 6. ПОРІВНЯННЯ ВКАЗІВНИКІВ
    a, b := 10, 10
    ptrA, ptrB := &a, &b
    ptrA2 := &a
    
    fmt.Printf("ptrA == ptrB: %v (різні адреси)\n", ptrA == ptrB)
    fmt.Printf("ptrA == ptrA2: %v (одна й та сама адреса)\n", ptrA == ptrA2)
    fmt.Printf("*ptrA == *ptrB: %v (однакові значення)\n", *ptrA == *ptrB)
    
    // 7. ВКАЗІВНИКИ НА МАСИВИ ТА ЗРІЗИ
    arr := [3]int{1, 2, 3}
    arrPtr := &arr
    fmt.Printf("Масив через вказівник: %v\n", *arrPtr)
    
    // Для зрізів вказівники використовуються рідше, бо зрізи самі по собі
    // містять вказівник на масив
    slice := []int{10, 20, 30}
    slicePtr := &slice
    (*slicePtr)[0] = 100
    fmt.Printf("Зріз після зміни через вказівник: %v\n", slice)
    
    // 8. NEW() ФУНКЦІЯ ДЛЯ СТВОРЕННЯ ВКАЗІВНИКІВ
    // Функція new() виділяє пам'ять та повертає вказівник на нульове значення
    newPtr := new(int)
    fmt.Printf("Вказівник через new(): адреса=%p, значення=%d\n", newPtr, *newPtr)
    *newPtr = 999
    fmt.Printf("Після присвоєння: *newPtr=%d\n", *newPtr)
    
    // 9. ВКАЗІВНИКИ ТА GC (GARBAGE COLLECTOR)
    // Go має автоматичний збірник сміття, тому не потрібно явно звільняти пам'ять
    // Вказівники допомагають уникати копіювання великих структур
    
    // 10. ПРАКТИЧНІ ПРИКЛАДИ
    fmt.Println("\n=== Практичні приклади ===")
    
    // Велика структура - передаємо вказівник, щоб уникнути копіювання
    type BigStruct struct {
        data [1000]int
    }
    
    processBigStruct := func(bs *BigStruct) {
        bs.data[0] = 999
    }
    
    big := BigStruct{}
    processBigStruct(&big)
    fmt.Printf("Велика структура оброблена: big.data[0]=%d\n", big.data[0])
    
    // Методи з pointer receiver
    type Counter struct {
        value int
    }
    
    // Метод з pointer receiver може змінювати структуру
    func (c *Counter) Increment() {
        c.value++
    }
    
    func (c *Counter) GetValue() int {
        return c.value
    }
    
    counterObj := Counter{value: 0}
    counterObj.Increment()
    counterObj.Increment()
    fmt.Printf("Лічильник: %d\n", counterObj.GetValue())
    
    fmt.Println("\n=== ВИСНОВКИ ===")
    fmt.Println("1. Вказівники дозволяють працювати з адресами пам'яті")
    fmt.Println("2. Оператор & отримує адресу, оператор * розіменовує")
    fmt.Println("3. Вказівники дозволяють змінювати оригінальні значення")
    fmt.Println("4. Нільні вказівники потребують обережного поводження")
    fmt.Println("5. Використовуйте вказівники для великих структур")
    fmt.Println("6. Pointer receivers дозволяють методам змінювати структуру")
}