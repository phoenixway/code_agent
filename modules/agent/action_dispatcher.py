"""Диспетчер виконання дій з оптимізацією контексту."""

import ast
import asyncio

class ActionDispatcher:
    def __init__(self, agent):
        self.agent = agent
        self.ui = agent.ui
        self.processor = agent.processor
        self.config = agent.config
        
        # Мапінг команд до методів відображення/обробки
        self._handlers = {
            'run_shell': self._handle_shell,
            'read_file': self._handle_read_file,
            'edit_file': self._handle_edit_file,
            'create_file': self._handle_create_file,
        }

    async def dispatch_segments(self, segments, state):
        """Обробляє список сегментів, виконує дії та повертає результати."""
        processed_segments = []
        system_results = []
        should_stop = False
        
        for segment in segments:
            if segment.type == 'thought':
                await self.ui.print_thought(segment.content)
                processed_segments.append(segment)
                
            elif segment.type == 'text':
                await self.ui.print_message(segment.content, role="assistant")
                processed_segments.append(segment)
                
            elif segment.type == 'action':
                # Виконання дії
                cmd_copy, result_text, stop_flag = await self._execute_action(segment.content, state)
                
                # Додаємо команду в історію
                segment.content = cmd_copy
                processed_segments.append(segment)
                
                system_results.append(result_text)
                if stop_flag:
                    should_stop = True
        
        return processed_segments, system_results, should_stop

    async def _execute_action(self, command, state):
        """Виконує одну дію, керує UI та повертає результат."""
        cmd_type = command.get("type") or command.get("action", "unknown")
        
        # 1. Loop Detection
        state.update_loop_tracker(command, "pending")
        if state.consecutive_failed_repeats >= 1:
            await self.ui.print_error("⚠️ Loop detected: Repeating failed action.")
            # Тут ми повертаємо True (stop), бо агент зациклився і йому треба допомога людини
            return command, "SYSTEM: CRITICAL Loop detected. Change strategy.", True

        # 2. UI Execution Wrapper
        handler = self._handlers.get(cmd_type, self._handle_default)
        result = await handler(command)
        
        # 3. Post-Processing
        output_text = result.get('output', '')
        status = result.get('status')
        state.update_loop_tracker(command, status)

        # 4. Syntax Check (Linting)
        if cmd_type in ['create_file', 'edit_file'] and status == 'success':
            path = command.get('path', '')
            if path.endswith('.py'):
                lint_error = self._check_python_syntax(path)
                if lint_error:
                    output_text += f"\n\n⚠️ SYSTEM WARNING: Syntax check failed for {path}:\n{lint_error}\nPlease fix this immediately."
                    # Ми НЕ змінюємо статус на error тут глобально, але даємо попередження
                    # status = 'error' 

        # 5. History Handling
        command_for_history = command.copy()

        # 6. Smart Stop Logic (ВИПРАВЛЕНО)
        is_state_changing = cmd_type in self.config.STATE_CHANGING_OPS
        execution_failed = status in ["failed", "error"]
        action_denied = status == "denied"
        
        should_stop = False
        
        if action_denied:
            # Якщо користувач заборонив - стоп
            output_text += "\n[SYSTEM: Action denied by user.]"
            should_stop = True
            
        elif execution_failed:
            # Якщо помилка - ПРОДОВЖУЄМО (повертаємо контроль агенту для виправлення)
            output_text += "\n[SYSTEM: Action failed. Analyze the error in <think> and retry.]"
            should_stop = False 
            
        elif is_state_changing:
            # Якщо успішна дія, що змінює стан (create, delete, shell) - СТОП (щоб користувач глянув)
            # АЛЕ: Якщо ми в автономному циклі, Orchestrator може це ігнорувати,
            # проте Dispatcher радить зупинитись.
            should_stop = True
            
        full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"

        return command_for_history, full_result_text, should_stop

    # --- Specific Handlers ---

    async def _handle_shell(self, command):
        widget = await self.ui.print_shell_start(command)
        await self.ui.start_action(command.get("during_execution", "Executing shell..."))
        result = await self.processor.process_single_action(command)
        await self.ui.update_shell_result(widget, result)
        return result

    async def _handle_read_file(self, command):
        widget = await self.ui.print_read_file_start(command)
        await self.ui.start_action(f"Reading {command.get('path', 'file')}...")
        result = await self.processor.process_single_action(command)
        await self.ui.update_read_file_result(widget, result)
        return result

    async def _handle_edit_file(self, command):
        widget = await self.ui.print_edit_file_start(command)
        await self.ui.start_action(f"Editing {command.get('path', 'file')}...")
        result = await self.processor.process_single_action(command)
        await self.ui.update_edit_file_result(widget, result)
        return result
    
    async def _handle_create_file(self, command):
        await self.ui.print_tool_call(command)
        await self.ui.start_action(f"Creating {command.get('path')}...")
        result = await self.processor.process_single_action(command)
        
        if result.get("status") == "success":
             await self.ui.print_confirmation(f"File {command.get('path')} created.")
        else:
             await self.ui.print_command_result(result.get('output'))
        return result

    async def _handle_default(self, command):
        await self.ui.print_tool_call(command)
        if command.get("before_execution"):
            await self.ui.print_plan(command['before_execution'])
        
        await self.ui.start_action(command.get("during_execution", "Working..."))
        result = await self.processor.process_single_action(command)
        
        if result.get("status") == "success" and command.get("after_execution"):
            await self.ui.print_confirmation(command['after_execution'])
        
        await self.ui.print_command_result(result.get('output', ''))
        return result

    def _check_python_syntax(self, path):
        """Перевіряє синтаксис Python файлу без його виконання."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                source = f.read()
            ast.parse(source)
            return None
        except SyntaxError as e:
            return f"Line {e.lineno}: {e.msg}\n{e.text}"
        except Exception as e:
            return str(e)
