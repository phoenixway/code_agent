import unittest

from rich.console import Console

from modules.ui_components.plan_update_formatter import format_plan_update_compact


class TestPlanUpdateFormatter(unittest.TestCase):
    def test_normal_five_step_progress(self):
        renderable = format_plan_update_compact(
            {
                "completed": 1,
                "total": 5,
                "current_title": "Modify ViewModel for optimistic deletion",
                "changed_steps": [
                    {"id": "sg_1", "status": "done"},
                    {"id": "sg_2", "status": "in_progress"},
                ],
            },
            {"width": 24, "color": False},
        )
        self.assertEqual(
            "◆ 1/5 Modify ViewModel…\n█░░░░\n  sg_1 done\n  sg_2 in_progress\n\n",
            renderable.plain,
        )

    def test_zero_progress(self):
        renderable = format_plan_update_compact(
            {
                "completed": 0,
                "total": 5,
                "current_title": "Analyze existing deletion logic",
                "changed_steps": [
                    {"id": "sg_1", "status": "in_progress"},
                    {"id": "sg_2", "status": "todo"},
                ],
            },
            {"width": 26, "color": False},
        )
        self.assertEqual(
            "◆ 0/5 Analyze existing…\n░░░░░\n  sg_1 in_progress\n  sg_2 todo\n\n",
            renderable.plain,
        )

    def test_long_title_truncation_stays_within_width(self):
        renderable = format_plan_update_compact(
            {
                "completed": 2,
                "total": 5,
                "current_title": "Very long task title that should be truncated on narrow terminals",
                "changed_steps": [],
            },
            {"width": 20, "color": False},
        )
        first_line = renderable.plain.splitlines()[0]
        self.assertLessEqual(len(first_line), 20)
        self.assertTrue(first_line.startswith("◆ 2/5 "))
        self.assertTrue(first_line.endswith("…"))

    def test_total_steps_greater_than_ten_scales_bar(self):
        renderable = format_plan_update_compact(
            {
                "completed": 7,
                "total": 12,
                "current_title": "Scale bar",
                "changed_steps": [],
            },
            {"width": 40, "color": False},
        )
        lines = renderable.plain.splitlines()
        self.assertEqual(10, len(lines[1]))
        self.assertEqual("█████░░░░░", lines[1])

    def test_no_changed_steps(self):
        renderable = format_plan_update_compact(
            {
                "completed": 3,
                "total": 3,
                "current_title": "Done",
                "changed_steps": [],
            },
            {"width": 40, "color": False},
        )
        self.assertEqual("◆ 3/3 Done\n███\n\n", renderable.plain)

    def test_color_disabled_renders_without_ansi(self):
        renderable = format_plan_update_compact(
            {
                "completed": 1,
                "total": 5,
                "current_title": "Modify ViewModel for optimistic deletion",
                "changed_steps": [{"id": "sg_1", "status": "done"}],
            },
            {"width": 40, "color": False},
        )
        console = Console(force_terminal=True, color_system="truecolor", record=True)
        console.print(renderable, end="")
        output = console.export_text(styles=True)
        self.assertNotIn("\x1b[", output)


if __name__ == "__main__":
    unittest.main()
