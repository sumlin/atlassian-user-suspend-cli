#!/usr/bin/env python3
"""
Тестирование подключения к Atlassian API
"""

import os
import sys
import requests
from dotenv import load_dotenv

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def test_connection():
    """Тестирование подключения и прав доступа"""
    console = Console() if RICH_AVAILABLE else None

    # Загрузка конфигурации
    load_dotenv()
    org_id = os.getenv("ORG_ID")
    api_key = os.getenv("API_KEY")

    print("🔍 Atlassian API Connection Test\n")

    # Проверка переменных окружения
    if not org_id or not api_key:
        error_msg = "❌ Не найдены переменные окружения ORG_ID или API_KEY"
        if console:
            console.print(Panel(error_msg, style="red"))
        else:
            print(error_msg)
        print("\nСоздайте файл .env со следующим содержимым:")
        print("ORG_ID=your-organization-id")
        print("API_KEY=your-api-key")
        return False

    print(f"📋 Organization ID: {org_id}")
    print(f"🔑 API Key: {'*' * 10}{api_key[-4:]}\n")

    # Тестирование различных эндпоинтов
    tests = [
        {
            "name": "Проверка доступа к организации",
            "url": f"https://api.atlassian.com/admin/v2/orgs/{org_id}/directories",
            "params": {},
            "check_permission": True
        },
        {
            "name": "Проверка прав на управление пользователями", 
            "url": f"https://api.atlassian.com/admin/v1/orgs/{org_id}/users",
            "params": {"limit": 1},
            "check_permission": False
        }
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    all_passed = True

    for test in tests:
        print(f"🧪 {test['name']}...")

        try:
            response = requests.get(
                test["url"],
                headers=headers,
                params=test["params"],
                timeout=10
            )

            if response.status_code == 200:
                success_msg = "   ✅ Успешно"
                if console:
                    console.print(success_msg, style="green")
                else:
                    print(success_msg)

                if test["check_permission"]:
                    data = response.json()
                    if "directories" in test["url"]:
                        # Для /directories показываем информацию о директориях
                        directories_data = data.get("data", [])
                        dir_count = len(directories_data)
                        print(f"   📊 Найдено директорий: {dir_count}")
                        
                        if directories_data and RICH_AVAILABLE and console:
                            directory = directories_data[0]
                            table = Table(title="Пример данных директории", show_header=True)
                            table.add_column("Поле", style="cyan")
                            table.add_column("Значение", style="yellow")

                            table.add_row("ID директории", directory.get("directoryId", "N/A"))
                            table.add_row("Название", directory.get("name", "N/A"))

                            console.print(table)
                    else:
                        # Для /users показываем информацию о пользователях
                        users_data = data.get("data", [])
                        user_count = len(users_data)
                        print(f"   📊 Найдено пользователей: {user_count}")

                        # Показываем пример данных первого пользователя
                        if users_data and RICH_AVAILABLE and console:
                            user = users_data[0]
                            table = Table(title="Пример данных пользователя", show_header=True)
                            table.add_column("Поле", style="cyan")
                            table.add_column("Значение", style="yellow")

                            table.add_row("Email", user.get("email", "N/A"))
                            table.add_row("Account ID", user.get("account_id", "N/A"))
                            table.add_row("Имя", user.get("name", "N/A"))
                            table.add_row("Статус", user.get("account_status", "N/A"))
                            table.add_row("Оплачиваемый", str(user.get("access_billable", False)))

                            products = user.get("product_access", [])
                            if products:
                                product_names = [p.get("name", p.get("key", "?")) for p in products]
                                table.add_row("Продукты", ", ".join(product_names))

                            console.print(table)

            elif response.status_code == 401:
                error_msg = "   ❌ Ошибка аутентификации: Неверный API ключ"
                if console:
                    console.print(error_msg, style="red")
                else:
                    print(error_msg)
                all_passed = False

            elif response.status_code == 403:
                error_msg = "   ❌ Недостаточно прав: Требуются права Organization Admin"
                if console:
                    console.print(error_msg, style="red")
                else:
                    print(error_msg)
                all_passed = False

            elif response.status_code == 404:
                error_msg = f"   ❌ Организация с ID '{org_id}' не найдена"
                if console:
                    console.print(error_msg, style="red")
                else:
                    print(error_msg)
                all_passed = False

            else:
                error_msg = f"   ❌ Неожиданный ответ: HTTP {response.status_code}"
                if console:
                    console.print(error_msg, style="yellow")
                else:
                    print(error_msg)
                print(f"   Ответ: {response.text[:200]}...")

        except requests.RequestException as e:
            error_msg = f"   ❌ Ошибка сети: {e}"
            if console:
                console.print(error_msg, style="red")
            else:
                print(error_msg)
            all_passed = False

        print()

    # Итоговый результат
    if all_passed:
        success_msg = "✅ Все тесты пройдены успешно! Подключение настроено правильно."
        if console:
            console.print(Panel(success_msg, style="green", title="Результат"))
        else:
            print("\n" + "=" * 50)
            print(success_msg)
            print("=" * 50)
    else:
        error_msg = "❌ Некоторые тесты не пройдены. Проверьте настройки."
        if console:
            console.print(Panel(error_msg, style="red", title="Результат"))
        else:
            print("\n" + "=" * 50)
            print(error_msg)
            print("=" * 50)

        print("\n💡 Рекомендации:")
        print("1. Убедитесь, что API ключ создан БЕЗ scope")
        print("2. Проверьте, что у вас есть права Organization Admin")
        print("3. Убедитесь, что Organization ID правильный")
        print("4. Проверьте, что домен вашей организации верифицирован")

    return all_passed


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)