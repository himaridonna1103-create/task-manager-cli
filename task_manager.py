# task_manager.py
import json
import os

SAVE_FILE = os.path.join(os.path.dirname(__file__), "tasks.json")


def load_tasks() -> list:
    if not os.path.exists(SAVE_FILE):
        return []
    with open(SAVE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"警告: tasks.json の読み込みに失敗しました ({e})。空のリストで起動します。")
            return []


def save_tasks(tasks: list) -> None:
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def add_task(title: str) -> str:
    if not title:
        return "タイトルを入力してください。"
    if len(title) > 200:
        return "タイトルは200文字以内にしてください。"
    tasks = load_tasks()
    next_id = max((t["id"] for t in tasks), default=0) + 1
    task = {"id": next_id, "title": title, "done": False}
    tasks.append(task)
    save_tasks(tasks)
    return f"追加しました: {title}"


def list_tasks() -> str:
    tasks = load_tasks()
    if not tasks:
        return "タスクはありません。"
    lines = []
    for task in tasks:
        status = "✅" if task["done"] else "⬜"
        lines.append(f"{status} [{task['id']}] {task['title']}")
    return "\n".join(lines)


def complete_task(task_id: int) -> str:
    tasks = load_tasks()
    for task in tasks:
        if task["id"] == task_id:
            if task["done"]:
                return f"ID {task_id} はすでに完了済みです。"
            task["done"] = True
            save_tasks(tasks)
            return f"完了しました: {task['title']}"
    return f"ID {task_id} のタスクが見つかりません。"


def delete_task(task_id: int) -> str:
    tasks = load_tasks()
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        return f"ID {task_id} のタスクが見つかりません。"
    save_tasks(new_tasks)
    return f"ID {task_id} を削除しました。"


def main():
    print("=== タスク管理アプリ ===")
    print("コマンド: add / list / done / delete / quit")

    while True:
        command = input("\n> ").strip()

        if command == "quit":
            print("終了します。")
            break
        elif command == "list":
            print(list_tasks())
        elif command.startswith("add "):
            title = command[4:].strip()
            print(add_task(title))
        elif command.startswith("done "):
            try:
                task_id = int(command[5:].strip())
                print(complete_task(task_id))
            except ValueError:
                print("IDには整数を入力してください。例: done 1")
        elif command.startswith("delete "):
            try:
                task_id = int(command[7:].strip())
                print(delete_task(task_id))
            except ValueError:
                print("IDには整数を入力してください。例: delete 1")
        else:
            print("不明なコマンドです。add / list / done / delete / quit")


if __name__ == "__main__":
    main()
