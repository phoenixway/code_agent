package com.example

import java.util.Date

// This is a sample Kotlin file for testing
class Person(
    val name: String,
    var age: Int
) {
    fun greet(): String {
        return "Hello, my name is $name"
    }
    
    fun celebrateBirthday() {
        age++
        println("Happy birthday! Now I'm $age years old.")
    }
}

interface Greetable {
    fun greet(): String
}

object SingletonExample {
    const val VERSION = "1.0"
    
    fun printVersion() {
        println("Version: $VERSION")
    }
}

fun main() {
    val person = Person("Alice", 30)
    println(person.greet())
    person.celebrateBirthday()
}

// Extension function
fun String.addExclamation(): String = this + "!"

// Data class
data class User(val id: Int, val username: String)

// Sealed class
sealed class Result {
    data class Success(val data: String) : Result()
    data class Error(val message: String) : Result()
}