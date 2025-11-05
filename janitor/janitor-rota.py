from datetime import datetime, timedelta
import csv

FILENAME = "janitor-rota.txt"


def get_current_and_next_week_person(filename):
    """
    Read the schedule file and determine who is on rota this week and next week.

    Args:
        filename: Path to the CSV file containing the schedule

    Returns:
        tuple: (current_week_person, current_start, current_end, next_week_person, next_start, next_end)
    """
    # Get today's date
    today = datetime.now().date()

    # Read the schedule file
    schedule = []
    with open(filename, "r") as file:
        reader = csv.DictReader(file, delimiter="\t")
        for row in reader:
            start_date = datetime.strptime(row["Start date"], "%m/%d/%Y").date()
            person = row["Person"]
            schedule.append((start_date, person))

    # Sort by date to ensure correct order
    schedule.sort(key=lambda x: x[0])

    # Find current week's person
    current_person = None
    current_start = None
    current_end = None
    next_person = None
    next_start = None
    next_end = None

    for i, (start_date, person) in enumerate(schedule):
        # Each rotation is Monday to Friday (4 days after start)
        end_date = start_date + timedelta(days=4)

        if start_date <= today <= end_date:
            current_person = person
            current_start = start_date
            current_end = end_date

            # Get next person from the schedule
            if i + 1 < len(schedule):
                next_person = schedule[i + 1][1]
                next_start = schedule[i + 1][0]
                next_end = next_start + timedelta(days=4)
            break

    return current_person, current_start, current_end, next_person, next_start, next_end


def format_date_range(start_date, end_date):
    """
    Format date range as 'DD-DD.MM' or 'DD.MM-DD.MM' if months differ.

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        str: Formatted date range
    """
    if start_date.month == end_date.month:
        return f"{start_date.day}-{end_date.day}.{start_date.month:02d}"
    else:
        return f"{start_date.day}.{start_date.month:02d}-{end_date.day}.{end_date.month:02d}"


if __name__ == "__main__":

    try:
        current, current_start, current_end, next_week, next_start, next_end = get_current_and_next_week_person(
            FILENAME
        )

        print(f"🗓️  Janitor ROTA")
        print(f"=" * 40)

        if current and current_start and current_end:
            current_range = format_date_range(current_start, current_end)
            print(f"This week ({current_range}):  {current}")
        else:
            print("This week:  No assignment found")

        if next_week and next_start and next_end:
            next_range = format_date_range(next_start, next_end)
            print(f"Next week ({next_range}):  {next_week}")
        else:
            print("Next week:  No assignment found")

        print(f"=" * 40)

    except FileNotFoundError:
        print(f"Error: Could not find file '{FILENAME}'")
    except Exception as e:
        print(f"Error: {e}")
