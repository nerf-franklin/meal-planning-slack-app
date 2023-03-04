import os
import requests
import json
import re
import logging
import time
import datetime
import threading
from slack_bolt import App
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

g_logger = logging.getLogger()


# Initialize app with bot token and signing secret
app = App(
    process_before_response=True,
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Spoonacular Configs
SPOONACULAR_BASE_URL = os.environ.get("SPOONACULAR_BASE_URL")
SPOONACULAR_API_KEY = os.environ.get("SPOONACULAR_API_KEY")
SPOONACULAR_HEADERS = {
    "Content-Type": 'application/json'
}
SPOON_BOT_CONVO_CONTEXT_ID = "112233445566778899"
USER_INFO = {
    "username": os.environ.get("USER_NAME"),
    "hash": os.environ.get("USER_HASH")
}

# Default Configs
GENERATE_MEAL_PLAN_OPTIONS = {
    "timeFrame": "Day",
    "targetCalories": 1000,
    "diet": ""
}

RANDOM_RECIPE = {}

# Canned responses
SAY_INVALID_CMD = "Sorry, I didn't recognize that command.  Please use `/nickbot guide` to see available commands."
SAY_SHOP_LIST_EMPTY = "Uh oh!  Your shopping list is currently *empty*.  Better start adding items..."

# Original images
EMPTY_DINNER_PLATE_IMG = os.environ.get("EMPTY_DINNER_PLATE_IMG")
EMPTY_SHOPPING_CART_IMG = os.environ.get("EMPTY_SHOPPING_CART_IMG")
SALAD_PLATE_IMG = os.environ.get("SALAD_PLATE_IMG")
SALAD_BOWL_IMG = os.environ.get("SALAD_BOWL_IMG")

# # # # # # # # # # # # # # # # # #
# #    DISPLAY / FORMATTING     # #
# # # # # # # # # # # # # # # # # #

block_divider = {
    "type": "divider"
}

welcome_home_block = {
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": "*Welcome Home!* \n\nHere you can view and modify your shopping list and meal plans... let's get healthy!"
    },
    "accessory": {
        "type": "image",
        "image_url": SALAD_BOWL_IMG,
        "alt_text": "Salad bowl image"
    }
}

home_view_main_nav_buttons = {
    "type": "actions",
    "block_id": "home_main_menu_block",
    "elements": [
        {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "Shopping List"
            },
            "value": "home_view_shop_list_val",
            "action_id": "home_view_shop_list_action",
            "style": "primary"
        },
        {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "Meal Plan Calendar"
            },
            "value": "home_view_meal_plans_val",
            "action_id": "home_view_meal_plans_action",
            "style": "primary"
        },
        {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "Recipes"
            },
            "value": "home_view_recipes_val",
            "action_id": "home_view_recipes_action",
            "style": "primary"
        }
    ]
}


# Create block to display nutrient info
def create_nutrient_display_block(nutrients: dict) -> dict:
    block_json = {
        "blocks": [
            block_divider,
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Nutrients:*\nCalories: {nutrients.get('calories')}, Protein: {nutrients.get('protein')},"
                            f" Fat: {nutrients.get('fat')}, Carbs: {nutrients.get('carbohydrates')}"
                }
            }
        ]
    }

    return block_json


# Create block to display aisle info
def create_sorted_aisles_display_block(aisles: dict) -> dict:
    total_items = 0
    for aisle in aisles:
        total_items += len(aisle.get("items"))

    block_json = {"blocks": []}

    block_json.get("blocks").append(block_divider)
    block_json.get("blocks").append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Sorted Shopping List ({total_items} items)"
            }
        }
    )
    for aisle in aisles:
        items_list = []
        for item in aisle.get("items"):
            items_list.append(f"{item.get('name')} ({item.get('measures').get('original').get('amount')}"
                              f" {item.get('measures').get('original').get('unit')})")
        items_joined = ", ".join(items_list)
        block_json.get("blocks").append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{aisle.get('aisle')}*\n{items_joined}"
                }
            }
        )

    return block_json


# Create blocks to display daily meal plan with nutrient info
def display_daily_meal_plan_and_nutrients(daily_plan_info: dict) -> dict:
    block_json = {"blocks": []}

    block_json.get("blocks").append(block_divider)
    block_json.get("blocks").append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Single day meal plan:"
            }
        }
    )

    nutrients = daily_plan_info.get("nutrients")
    meal_ids = []

    for meal in daily_plan_info.get("meals"):
        meal_id = meal.get('id')
        meal_ids.append(str(meal_id))
        full_recipe = get_recipe_by_id(meal_id)
        meal_img = full_recipe.get('image')

        if full_recipe.get("summary"):
            summary = full_recipe.get("summary").replace('<b>', '*').replace('</b>', '*')
            summary = re.sub(r'<.*?', '', summary)
            summary = f"{summary[:180]}..."
        else:
            summary = "No summary found..."

        vegan = "*V*" if full_recipe.get('vegan') else ""
        vegetarian = "*Veg*" if full_recipe.get('vegetarian') else ""
        gluten_free = "*GF*" if full_recipe.get('glutenFree') else ""
        dairy_free = "*DF*" if full_recipe.get('dairyFree') else ""

        category_str = "None Found" if not vegan and not vegetarian and not gluten_free and not dairy_free else\
            f"{vegan} {vegetarian} {gluten_free} {dairy_free}"

        block_json.get("blocks").append(block_divider)
        block_json.get("blocks").append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{meal.get('title')}"
                }
            }
        )
        block_json.get("blocks").append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{summary}\nReady In: {meal.get('readyInMinutes')} minutes | Servings:"
                            f" {meal.get('servings')}\t{category_str}"
                },
                "accessory": {
                    "type": "image",
                    "image_url": meal_img,
                    "alt_text": f"Meal Img"
                },
                "block_id": f"daily_meal_plan_item_{str(meal_id)}_{meal.get('title')}_{meal.get('servings')}"
            }
        )
        block_json.get("blocks").append(
            {
                "type": "actions",
                "block_id": f"daily_meal_plan_view_source_{str(meal_id)}_action",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Source"
                        },
                        "value": str(meal_id),
                        "action_id": "daily_meal_plan_view_source",
                        "url": meal.get('sourceUrl')
                    }
                ]
            }
        )

    block_json.get("blocks").append(block_divider)
    block_json.get("blocks").append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Combined Nutrients:*\n*Calories*: {nutrients.get('calories')},"
                        f" *Protein*: {nutrients.get('protein')},"
                        f" *Fat*: {nutrients.get('fat')}, *Carbs*: {nutrients.get('carbohydrates')}\n"
            }
        }
    )
    block_json.get("blocks").append(
        {
            "type": "section",
            "block_id": "meal_plan_date_picker_section",
            "text": {
                "type": "mrkdwn",
                "text": "Select a date to add meal plan (all 3 meals will be added):"
            },
            "accessory": {
                "type": "datepicker",
                "action_id": "meal_plan_date_picker",
                "initial_date": "2022-10-07",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select a date"
                }
            }
        }
    )
    block_json.get("blocks").append(block_divider)
    return block_json


# Create blocks to display detailed nutrient info for an ingredient
def display_nutrition_details_for_ingredient(ingredient: dict) -> dict:
    block_json = {"blocks": []}
    name = ingredient.get("name")
    if ingredient.get("nutrition"):
        nutrition = ingredient.get("nutrition")
        nutrients = nutrition.get("nutrients")
        # properties = nutrition.get("properties")
        # flavonoids = nutrition.get("flavonoids")

        block_json.get("blocks").append(block_divider)
        block_json.get("blocks").append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Nutrition Info - {name.capitalize()}"
                }
            }
        )

        for nutrient in nutrients:
            block_json.get("blocks").append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{nutrient.get('name')} - {nutrient.get('amount')} {nutrient.get('unit')} |"
                                f" {nutrient.get('percentOfDailyNeeds')}% DV"
                    }
                }
            )

        return block_json


# Append detailed nutrient info to existing blocks list (for nutrient modal update)
def append_nutrient_info_to_block_list(blocks: list, ingredient: dict) -> list:
    block_list = blocks
    name = ingredient.get("name")
    if ingredient.get("nutrition"):
        nutrition = ingredient.get("nutrition")
        nutrients = nutrition.get("nutrients")
        # properties = nutrition.get("properties")
        # flavonoids = nutrition.get("flavonoids")

        block_list.append(block_divider)
        block_list.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Nutrition Info - {name.capitalize()}"
                }
            }
        )

        for nutrient in nutrients:
            block_list.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{nutrient.get('name')} - {nutrient.get('amount')} {nutrient.get('unit')} |"
                                f" {nutrient.get('percentOfDailyNeeds')}% DV"
                    }
                }
            )

        return block_list


# Combine duplicates items in list and update amounts - needed?
def combine_duplicate_items(items: list):
    new_list = []
    # TO DO
    return


# Lazy listener ack
def lazy_listener_ack(body, ack):
    ack()


# # # # # # # # # # # # # # # # # #
# #    SPOONACULAR REQUESTS     # #
# # # # # # # # # # # # # # # # # #


# Get user info
def load_user_info(username: str):
    global USER_INFO

    if USER_INFO["hash"] in ["hash"]:

        url_path = "/users/connect"
        url = f"{SPOONACULAR_BASE_URL}{url_path}"
        params = {
            'apiKey': SPOONACULAR_API_KEY,
        }
        payload = {
            "username": username
        }

        response = requests.post(url=url, json=payload, headers=SPOONACULAR_HEADERS, params=params)
        response_json = json.loads(response.content)

        g_logger.debug(f"Response from POST user connect: {response_json}")

        USER_INFO['username'] = response_json.get("username")
        USER_INFO['hash'] = response_json.get("hash")

    else:
        g_logger.debug("User info has already been loaded...")

    return


# List all items in shopping list
def list_items_in_shopping_list() -> dict:
    global USER_INFO
    # load_user_info("nick_test")
    username = USER_INFO["username"]
    user_hash = USER_INFO["hash"]
    url_path = f"/mealplanner/{username}/shopping-list"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'hash': user_hash
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from GET items in shopping list: {json.loads(response.content)}")

    return json.loads(response.content)


# Add item to shopping list
def add_item_to_shopping_list(item: str, parse: bool) -> dict:
    global USER_INFO
    # load_user_info("nick_test")
    username = USER_INFO["username"]
    user_hash = USER_INFO["hash"]
    url_path = f"/mealplanner/{username}/shopping-list/items"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'hash': user_hash
    }
    payload = {
        "item": item,
        "parse": parse  # Will attempt to parse and analyze item or not
    }

    response = requests.post(url=url, json=payload, headers=SPOONACULAR_HEADERS, params=params)
    response_json = json.loads(response.content)

    g_logger.debug(f"Response from POST add to shopping list: {response_json}")

    return response_json


# Delete item from shopping list by name
def delete_item_from_shopping_list(item_name: str) -> dict:
    g_logger.debug(f"Starting to delete {item_name} from shopping list.")
    item_id = get_list_item_id_by_name(item_name)

    if item_id != "":
        global USER_INFO
        # load_user_info("nick_test")
        username = USER_INFO["username"]
        user_hash = USER_INFO["hash"]
        url_path = f"/mealplanner/{username}/shopping-list/items/{item_id}"
        url = f"{SPOONACULAR_BASE_URL}{url_path}"
        params = {
            'apiKey': SPOONACULAR_API_KEY,
            'hash': user_hash
        }

        response = requests.delete(url=url, headers=SPOONACULAR_HEADERS, params=params)
        response_json = json.loads(response.content)

        g_logger.debug(f"Response from DEL remove item from shopping list: {response_json}")

        return response_json
    else:
        return {
            "not_found": item_name
        }


# Empty shopping list
def empty_shopping_list() -> dict:
    g_logger.debug("Starting to empty shopping list")
    total_deleted = 0
    list_response = list_items_in_shopping_list()
    if len(list_response) > 0:
        for aisle in list_response.get("aisles"):
            for item in aisle.get("items"):
                delete_item_from_shopping_list(item.get("name"))
                total_deleted += total_deleted
    return {
        "total_deleted": total_deleted
    }


# Get shopping list item id from name
def get_list_item_id_by_name(item_name: str) -> dict:
    item_id = ""
    current_list = list_items_in_shopping_list()
    for aisle in current_list.get("aisles"):
        for item in aisle.get("items"):
            if item.get("name").lower() == item_name.lower():
                item_id = item.get("id")
                break
    return item_id


# Search all recipes using natural language search query
def search_all_recipes(query: str) -> dict:
    url_path = "/recipes/complexSearch"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'query': query
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from GET recipes search: {json.loads(response.content)}")

    return json.loads(response.content)


# Search all recipes by ingredients list
def search_all_recipes_by_ingredients(ingredients: list) -> dict:
    # Change list to comma separated string for params
    comma_sep_ingredients = ",".join(ingredients)

    url_path = "/recipes/findByIngredients"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'ingredients': comma_sep_ingredients,
        'number': 5,
        'ignorePantry': True
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from GET recipes by ingredients search: {json.loads(response.content)}")

    return json.loads(response.content)


# Get random recipe
def get_random_recipe() -> dict:
    url_path = "/recipes/random"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from GET random recipe: {json.loads(response.content)}")

    return json.loads(response.content)


# GET user's existing meal plan for a specific WEEK
# Start date must be in the format yyyy-mm-dd
def get_meal_plan_for_week(start_date: str) -> dict:
    global USER_INFO
    # load_user_info("nick_test")
    username = USER_INFO["username"]
    user_hash = USER_INFO["hash"]
    url_path = f"/mealplanner/{username}/week/{start_date}"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'hash': user_hash
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from GET meal plan for the week: {json.loads(response.content)}")

    return json.loads(response.content)


# GET user's existing meal plan for a specific DAY
# Start date must be in the format yyyy-mm-dd
def get_meal_plan_for_day(date: str) -> dict:
    global USER_INFO
    # load_user_info("nick_test")
    username = USER_INFO["username"]
    user_hash = USER_INFO["hash"]
    url_path = f"/mealplanner/{username}/day/{date}"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'hash': user_hash
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from GET meal plan for the day: {json.loads(response.content)}")

    return json.loads(response.content)


# Generate meal plan
def generate_meal_plan(time_frame: str, target_calories: int, diet: str, exclude: str) -> dict:
    url_path = "/mealplanner/generate"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'timeFrame': time_frame,
        'targetCalories': target_calories,
        'diet': diet,
        'exclude': exclude
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from Generate meal plan: {json.loads(response.content)}")

    return json.loads(response.content)


# Add a single item to the user's meal plan
def add_item_to_meal_plan(item_type: str, date: int, slot: int, position: int) -> dict:
    global USER_INFO
    # load_user_info("nick_test")
    username = USER_INFO["username"]
    user_hash = USER_INFO["hash"]
    url_path = f"/mealplanner/{username}/items"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'hash': user_hash
    }
    payload = {
        "type": item_type,
        "date": date,
        "slot": slot,
        "position": position,
        "value": {
            "id": "id",
            "servings": "servings",
            "title": "title",
            "imageType": "jpg"
        }
    }

    response = requests.post(url=url, json=payload, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from POST item to meal plan: {json.loads(response.content)}")

    return json.loads(response.content)


# Add multiple meals/recipes to the user's meal plan on a single day
def add_daily_meal_plan_to_calendar_day(selected_date: str, item_type: str, meals_list: list) -> dict:
    global USER_INFO
    # load_user_info("nick_test")
    username = USER_INFO["username"]
    user_hash = USER_INFO["hash"]
    url_path = f"/mealplanner/{username}/items"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'hash': user_hash
    }
    payload = []
    slot = 1

    # Convert from yyyy-mm-dd string to timestamp
    g_logger.debug(f"Selected date: {selected_date}")
    converted_date = datetime.datetime.strptime(selected_date, "%Y-%m-%d")
    timestamp = datetime.datetime.timestamp(converted_date)

    for meal in meals_list:
        payload.append(
            {
                "type": item_type,
                "date": timestamp,
                "slot": slot,
                "position": 1,
                "value": meal
            }
        )
        slot += 1

    g_logger.debug(f"Attempting to POST payload {payload} to meal planner...")
    response = requests.post(url=url, json=payload, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from POST items to meal plan for date {selected_date}: {json.loads(response.content)}")

    return json.loads(response.content)


# DELETE item from user's meal plan
def delete_item_from_meal_plan(item_id: int) -> dict:
    global USER_INFO
    username = USER_INFO["username"]
    user_hash = USER_INFO["hash"]
    url_path = f"/mealplanner/{username}/items/{item_id}"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'hash': user_hash
    }

    response = requests.delete(url=url, headers=SPOONACULAR_HEADERS, params=params)
    response_json = json.loads(response.content)

    g_logger.debug(f"Response from DEL remove item from meal plan: {response_json}")

    return response_json


# Search all ingredients
def search_all_ingredients(query: str) -> dict:
    url_path = "/food/ingredients/search"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'query': query,
        'addChildren': True,
        'number': 20
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from Search all ingredients: {json.loads(response.content)}")

    return json.loads(response.content)


# Talk to Spoonacular's chatbot - not currently working (Spoonacular 500 Error)
def talk_to_spoon_bot(text: str) -> dict:
    url_path = "/food/converse"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        "text": text,
        "contextId": SPOON_BOT_CONVO_CONTEXT_ID
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from Talk to Spoonacular bot: {json.loads(response.content)}")

    return json.loads(response.content)


# GET ingredient details by id
def get_ingredient_info_by_id(ingred_id: str) -> dict:
    url_path = f"/food/ingredients/{ingred_id}/information"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        'amount': 1
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from GET ingredient details: {json.loads(response.content)}")

    return json.loads(response.content)


# GET recipe details by id
def get_recipe_by_id(recipe_id: str) -> dict:
    url_path = f"/recipes/{recipe_id}/information"
    url = f"{SPOONACULAR_BASE_URL}{url_path}"
    params = {
        'apiKey': SPOONACULAR_API_KEY,
        "id": recipe_id,
        "includeNutrition": True
    }

    response = requests.get(url=url, headers=SPOONACULAR_HEADERS, params=params)

    g_logger.debug(f"Response from GET recipe details by id: {json.loads(response.content)}")

    return json.loads(response.content)


# Add all ingredients from a recipe to the shopping list
def add_recipe_ingredients_to_shop_list(recipe_id: str) -> dict:
    recipe_response = get_recipe_by_id(recipe_id)
    items_added = []
    total_added = 0
    extended_ingredients = recipe_response.get("extendedIngredients")
    for ingred in extended_ingredients:
        name = ingred.get("nameClean") if ingred.get("nameClean") else ingred.get("name")
        item_to_add = f"{ingred.get('amount')} {ingred.get('unit')} {name}"
        add_item_to_shopping_list(item_to_add, True)
        items_added.append(item_to_add)
        total_added = total_added + 1

    return {
        "recipe_id": recipe_id,
        "items_added": items_added,
        "total_added": total_added
    }


# Take response from GET meal plan week and restructure / simplify and enrich with img details
def convert_meal_plan_week_to_detailed_week(meal_plan_week: dict) -> dict:
    response = {}

    for day in meal_plan_week.get("days"):
        day_name = day.get("day")
        day_detail = {
            "breakfast": {
                "title": "No breakfast found...",
                "img_url": EMPTY_DINNER_PLATE_IMG,
                "servings": None
            },
            "lunch": {
                "title": "No lunch found...",
                "img_url": EMPTY_DINNER_PLATE_IMG,
                "servings": None
            },
            "dinner": {
                "title": "No dinner found...",
                "img_url": EMPTY_DINNER_PLATE_IMG,
                "servings": None
            }
        }

        for item in day.get("items"):
            slot = item.get("slot")
            recipe_id = item.get("value").get("id")
            servings = item.get("value").get("servings")
            title = item.get("value").get("title")
            img_url = get_recipe_by_id(str(recipe_id)).get("image")

            if slot == 1:
                day_detail['breakfast']['title'] = title
                day_detail['breakfast']['img_url'] = img_url
                day_detail['breakfast']['servings'] = servings
            if slot == 2:
                day_detail['lunch']['title'] = title
                day_detail['lunch']['img_url'] = img_url
                day_detail['lunch']['servings'] = servings
            if slot == 3:
                day_detail['dinner']['title'] = title
                day_detail['dinner']['img_url'] = img_url
                day_detail['dinner']['servings'] = servings
        response[day_name] = day_detail

    return response


# # # # # # # # # # # # # # # # # #
# #    LISTENING TO EVENTS      # #
# # # # # # # # # # # # # # # # # #


# Publish main home view (default view shows the shopping list)
def publish_main_home_view(client, user):
    try:
        # Get shopping list
        list_response = list_items_in_shopping_list()
        items = []
        if len(list_response.get("aisles")) > 0:
            for aisle in list_response.get("aisles"):
                for item in aisle.get("items"):
                    items.append(f"{item.get('name')} ({item.get('measures').get('original').get('amount')}"
                                 f" {item.get('measures').get('original').get('unit')})")

            spaced_list = '\n'.join(items)
        else:
            spaced_list = SAY_SHOP_LIST_EMPTY

        # Publish main home view
        client.views_publish(
            user_id=user,
            view={
                "type": "home",
                "callback_id": "home_view",
                "blocks": [
                    welcome_home_block,
                    block_divider,
                    home_view_main_nav_buttons,
                    block_divider,
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Shopping List ({len(items)} items)"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{spaced_list}"
                        }
                    },
                    block_divider,
                    {
                        "type": "actions",
                        "block_id": "home_shop_list_actions_block",
                        "elements": [
                            {
                                "type": "external_select",
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "Search ingredients..."
                                },
                                "min_query_length": 2,
                                "action_id": "home_shop_list_search_ingred_action"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Add item to list"
                                },
                                "value": "home_add_item_list_val",
                                "action_id": "home_shop_list_add_item_action"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Remove item from list"
                                },
                                "value": "home_delete_item_list_val",
                                "action_id": "home_shop_list_delete_item_action"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Group items by aisle"
                                },
                                "value": "home_sort_list_val",
                                "action_id": "home_shop_list_sort_action"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Empty shopping list"
                                },
                                "value": "home_empty_list_val",
                                "action_id": "home_shop_list_empty_action",
                                "confirm": {
                                    "title": {
                                        "type": "plain_text",
                                        "text": "Are you sure?"
                                    },
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": "Remove all items from your shopping list?  (May take a few moments if there are many items)"
                                    },
                                    "confirm": {
                                        "type": "plain_text",
                                        "text": "Delete all items"
                                    },
                                    "deny": {
                                        "type": "plain_text",
                                        "text": "Cancel"
                                    }
                                }
                            }
                        ]

                    },
                ]
            }
        )

    except Exception as e:
        g_logger.error(f"Error publishing home tab: {e}")


# Publish main home view (default view shows the shopping list) - sorted list
def publish_main_home_view_sorted(client, user):
    try:
        # Get shopping list
        list_response = list_items_in_shopping_list()
        total_items = 0
        for aisle in list_response.get("aisles"):
            total_items += len(aisle.get("items"))

        # Creating blocks for view
        blocks_list = [
            welcome_home_block,
            block_divider,
            home_view_main_nav_buttons,
            block_divider,
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Sorted Shopping List ({total_items} items)"
                }
            }
        ]

        # creating category list
        for aisle in list_response.get("aisles"):
            items_list = []
            for item in aisle.get("items"):
                items_list.append(f"{item.get('name')} ({item.get('measures').get('original').get('amount')}"
                                  f" {item.get('measures').get('original').get('unit')})")
            items_joined = ", ".join(items_list)
            blocks_list.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{aisle.get('aisle')}*\n{items_joined}"
                    }
                }
            )

        blocks_list.append(block_divider)
        blocks_list.append(
            {
                "type": "actions",
                "block_id": "home_shop_list_actions_block",
                "elements": [
                    {
                        "type": "external_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Search ingredients..."
                        },
                        "min_query_length": 2,
                        "action_id": "home_shop_list_search_ingred_action"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Add item to list"
                        },
                        "value": "home_add_item_list_val",
                        "action_id": "home_shop_list_add_item_action"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Remove item from list"
                        },
                        "value": "home_delete_item_list_val",
                        "action_id": "home_shop_list_delete_item_action"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View ungrouped list"
                        },
                        "value": "home_unsort_list_val",
                        "action_id": "home_shop_list_unsort_action"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Empty shopping list"
                        },
                        "value": "home_empty_list_val",
                        "action_id": "home_shop_list_empty_action",
                        "confirm": {
                            "title": {
                                "type": "plain_text",
                                "text": "Are you sure?"
                            },
                            "text": {
                                "type": "mrkdwn",
                                "text": "Really remove all items from your shopping list?"
                            },
                            "confirm": {
                                "type": "plain_text",
                                "text": "Delete all items"
                            },
                            "deny": {
                                "type": "plain_text",
                                "text": "Cancel"
                            }
                        }
                    }
                ]

            }
        )

        # Publish sorted view
        client.views_publish(
            user_id=user,
            view={
                "type": "home",
                "callback_id": "home_view",
                "blocks": blocks_list
            }
        )

    except Exception as e:
        g_logger.error(f"Error publishing home tab: {e}")


# Publish meal plan pane on home view
def publish_meal_plan_home_view(client, user):
    try:

        # Loading screen
        client.views_publish(
            user_id=user,
            view={
                "type": "home",
                "callback_id": "home_view_meal_plans_loading",
                "blocks": [
                    welcome_home_block,
                    block_divider,
                    home_view_main_nav_buttons,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Loading meal plan calendar...*"
                        }
                    }
                ]
            }
        )

        # Get current time / date info
        today = datetime.datetime.now()
        today_adjusted_tz = today - datetime.timedelta(hours=7)
        current_month = today_adjusted_tz.strftime("%B")
        current_year = today_adjusted_tz.strftime("%Y")
        # 0 is sunday, 6 is saturday
        current_weekday = today_adjusted_tz.strftime("%w")
        g_logger.debug(
            f"Current time: {str(today)}. Adjusted time: {today_adjusted_tz}  Current week day: {current_weekday}")

        # Get start of current week
        if current_weekday == '1':
            start_of_current_week = today_adjusted_tz
            start_of_current_week_formatted = today_adjusted_tz.strftime("%Y-%m-%d")
            g_logger.debug(f"Start date of current week: {start_of_current_week_formatted}")
        else:
            day_offset = int(current_weekday) - 1 if current_weekday != '0' else 6
            start_of_current_week = today_adjusted_tz - datetime.timedelta(days=day_offset)
            start_of_current_week_formatted = start_of_current_week.strftime("%Y-%m-%d")
            g_logger.debug(f"Start date of current week: {start_of_current_week_formatted}")

        # Get user's existing meal plan for the current week
        # Start date must be in the format yyyy-mm-dd
        meal_plan_week_response = get_meal_plan_for_week(start_of_current_week_formatted)
        mp_week_converted = convert_meal_plan_week_to_detailed_week(meal_plan_week_response)
        g_logger.debug(f"Meal plan week converted json: {mp_week_converted}")
        g_logger.debug(f"Get meal plan for week {start_of_current_week_formatted} response: {meal_plan_week_response}")

        days_found_list = []
        for day in meal_plan_week_response.get("days"):
            days_found_list.append(day.get("day"))
        g_logger.debug(f"Days found for weekly meal plan: {days_found_list}")

        client.views_publish(
            user_id=user,
            view={
                "type": "home",
                "callback_id": "home_view_meal_plans",
                "blocks": [
                    welcome_home_block,
                    block_divider,
                    home_view_main_nav_buttons,
                    block_divider,
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Meal Plan Calendar - Current Week: {current_month} {current_year}"
                        }
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Monday* (Today)" if current_weekday == '1' else f"Monday {start_of_current_week.strftime('%b %d')}"
                        },
                        "accessory": {
                            "type": "overflow",
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "View details for Monday"
                                    },
                                    "value": f"{start_of_current_week_formatted}"
                                }
                            ],
                            "action_id": "mp_view_day"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Monday').get('breakfast').get('img_url')}" if mp_week_converted.get(
                                    'Monday') and mp_week_converted.get('Monday').get(
                                    'breakfast') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Monday').get('breakfast').get('title')}" if mp_week_converted.get(
                                    'Monday') and mp_week_converted.get('Monday').get(
                                    'breakfast') else f"No breakfast found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Monday').get('lunch').get('img_url')}" if mp_week_converted.get(
                                    'Monday') and mp_week_converted.get('Monday').get(
                                    'lunch') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Monday').get('lunch').get('title')}" if mp_week_converted.get(
                                    'Monday') and mp_week_converted.get('Monday').get('lunch') else f"No lunch found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Monday').get('dinner').get('img_url')}" if mp_week_converted.get(
                                    'Monday') and mp_week_converted.get('Monday').get(
                                    'dinner') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Monday').get('dinner').get('title')}" if mp_week_converted.get(
                                    'Monday') and mp_week_converted.get('Monday').get(
                                    'dinner') else f"No dinner found..."
                            }
                        ]
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Tuesday* (Today)" if current_weekday == '2' else f"Tuesday {(start_of_current_week + datetime.timedelta(days=1)).strftime('%b %d')}"
                        },
                        "accessory": {
                            "type": "overflow",
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "View details for Tuesday"
                                    },
                                    "value": f"{(start_of_current_week + datetime.timedelta(days=1)).strftime('%Y-%m-%d')}"
                                }
                            ],
                            "action_id": "mp_view_day"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Tuesday').get('breakfast').get('img_url')}" if mp_week_converted.get(
                                    'Tuesday') and mp_week_converted.get('Tuesday').get(
                                    'breakfast') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Tuesday').get('breakfast').get('title')}" if mp_week_converted.get(
                                    'Tuesday') and mp_week_converted.get('Tuesday').get(
                                    'breakfast') else f"No breakfast found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Tuesday').get('lunch').get('img_url')}" if mp_week_converted.get(
                                    'Tuesday') and mp_week_converted.get('Tuesday').get(
                                    'lunch') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Tuesday').get('lunch').get('title')}" if mp_week_converted.get(
                                    'Tuesday') and mp_week_converted.get('Tuesday').get(
                                    'lunch') else f"No lunch found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Tuesday').get('dinner').get('img_url')}" if mp_week_converted.get(
                                    'Tuesday') and mp_week_converted.get('Tuesday').get(
                                    'dinner') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Tuesday').get('dinner').get('title')}" if mp_week_converted.get(
                                    'Tuesday') and mp_week_converted.get('Tuesday').get(
                                    'dinner') else f"No dinner found..."
                            }
                        ]
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Wednesday* (Today)" if current_weekday == '3' else f"Wednesday {(start_of_current_week + datetime.timedelta(days=2)).strftime('%b %d')}"
                        },
                        "accessory": {
                            "type": "overflow",
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "View details for Wednesday"
                                    },
                                    "value": f"{(start_of_current_week + datetime.timedelta(days=2)).strftime('%Y-%m-%d')}"
                                }
                            ],
                            "action_id": "mp_view_day"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Wednesday').get('breakfast').get('img_url')}" if mp_week_converted.get(
                                    'Wednesday') and mp_week_converted.get('Wednesday').get(
                                    'breakfast') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Wednesday').get('breakfast').get('title')}" if mp_week_converted.get(
                                    'Wednesday') and mp_week_converted.get('Wednesday').get(
                                    'breakfast') else f"No breakfast found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Wednesday').get('lunch').get('img_url')}" if mp_week_converted.get(
                                    'Wednesday') and mp_week_converted.get('Wednesday').get(
                                    'lunch') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Wednesday').get('lunch').get('title')}" if mp_week_converted.get(
                                    'Wednesday') and mp_week_converted.get('Wednesday').get(
                                    'lunch') else f"No lunch found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Wednesday').get('dinner').get('img_url')}" if mp_week_converted.get(
                                    'Wednesday') and mp_week_converted.get('Wednesday').get(
                                    'dinner') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Wednesday').get('dinner').get('title')}" if mp_week_converted.get(
                                    'Wednesday') and mp_week_converted.get('Wednesday').get(
                                    'dinner') else f"No dinner found..."
                            }
                        ]
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Thursday* (Today)" if current_weekday == '4' else f"Thursday {(start_of_current_week + datetime.timedelta(days=3)).strftime('%b %d')}"
                        },
                        "accessory": {
                            "type": "overflow",
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "View details for Thursday"
                                    },
                                    "value": f"{(start_of_current_week + datetime.timedelta(days=3)).strftime('%Y-%m-%d')}"
                                }
                            ],
                            "action_id": "mp_view_day"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Thursday').get('breakfast').get('img_url')}" if mp_week_converted.get(
                                    'Thursday') and mp_week_converted.get('Thursday').get(
                                    'breakfast') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Thursday').get('breakfast').get('title')}" if mp_week_converted.get(
                                    'Thursday') and mp_week_converted.get('Thursday').get(
                                    'breakfast') else f"No breakfast found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Thursday').get('lunch').get('img_url')}" if mp_week_converted.get(
                                    'Thursday') and mp_week_converted.get('Thursday').get(
                                    'lunch') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Thursday').get('lunch').get('title')}" if mp_week_converted.get(
                                    'Thursday') and mp_week_converted.get('Thursday').get(
                                    'lunch') else f"No lunch found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Thursday').get('dinner').get('img_url')}" if mp_week_converted.get(
                                    'Thursday') and mp_week_converted.get('Thursday').get(
                                    'dinner') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Thursday').get('dinner').get('title')}" if mp_week_converted.get(
                                    'Thursday') and mp_week_converted.get('Thursday').get(
                                    'dinner') else f"No dinner found..."
                            }
                        ]
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Friday* (Today)" if current_weekday == '5' else f"Friday {(start_of_current_week + datetime.timedelta(days=4)).strftime('%b %d')}"
                        },
                        "accessory": {
                            "type": "overflow",
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "View details for Friday"
                                    },
                                    "value": f"{(start_of_current_week + datetime.timedelta(days=4)).strftime('%Y-%m-%d')}"
                                }
                            ],
                            "action_id": "mp_view_day"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Friday').get('breakfast').get('img_url')}" if mp_week_converted.get(
                                    'Friday') and mp_week_converted.get('Friday').get(
                                    'breakfast') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Friday').get('breakfast').get('title')}" if mp_week_converted.get(
                                    'Friday') and mp_week_converted.get('Friday').get(
                                    'breakfast') else f"No breakfast found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Friday').get('lunch').get('img_url')}" if mp_week_converted.get(
                                    'Friday') and mp_week_converted.get('Friday').get(
                                    'lunch') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Friday').get('lunch').get('title')}" if mp_week_converted.get(
                                    'Friday') and mp_week_converted.get('Friday').get('lunch') else f"No lunch found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Friday').get('dinner').get('img_url')}" if mp_week_converted.get(
                                    'Friday') and mp_week_converted.get('Friday').get(
                                    'dinner') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Friday').get('dinner').get('title')}" if mp_week_converted.get(
                                    'Friday') and mp_week_converted.get('Friday').get(
                                    'dinner') else f"No dinner found..."
                            }
                        ]
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Saturday* (Today)" if current_weekday == '6' else f"Saturday {(start_of_current_week + datetime.timedelta(days=5)).strftime('%b %d')}"
                        },
                        "accessory": {
                            "type": "overflow",
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "View details for Saturday"
                                    },
                                    "value": f"{(start_of_current_week + datetime.timedelta(days=5)).strftime('%Y-%m-%d')}"
                                }
                            ],
                            "action_id": "mp_view_day"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Saturday').get('breakfast').get('img_url')}" if mp_week_converted.get(
                                    'Saturday') and mp_week_converted.get('Saturday').get(
                                    'breakfast') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Saturday').get('breakfast').get('title')}" if mp_week_converted.get(
                                    'Saturday') and mp_week_converted.get('Saturday').get(
                                    'breakfast') else f"No breakfast found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Saturday').get('lunch').get('img_url')}" if mp_week_converted.get(
                                    'Saturday') and mp_week_converted.get('Saturday').get(
                                    'lunch') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Saturday').get('lunch').get('title')}" if mp_week_converted.get(
                                    'Saturday') and mp_week_converted.get('Saturday').get(
                                    'lunch') else f"No lunch found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Saturday').get('dinner').get('img_url')}" if mp_week_converted.get(
                                    'Saturday') and mp_week_converted.get('Saturday').get(
                                    'dinner') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Saturday').get('dinner').get('title')}" if mp_week_converted.get(
                                    'Saturday') and mp_week_converted.get('Saturday').get(
                                    'dinner') else f"No dinner found..."
                            }
                        ]
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Sunday* (Today)" if current_weekday == '0' else f"Sunday {(start_of_current_week + datetime.timedelta(days=6)).strftime('%b %d')}"
                        },
                        "accessory": {
                            "type": "overflow",
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "View details for Sunday"
                                    },
                                    "value": f"{(start_of_current_week + datetime.timedelta(days=6)).strftime('%Y-%m-%d')}"
                                }
                            ],
                            "action_id": "mp_view_day"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Sunday').get('breakfast').get('img_url')}" if mp_week_converted.get(
                                    'Sunday') and mp_week_converted.get('Sunday').get(
                                    'breakfast') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Sunday').get('breakfast').get('title')}" if mp_week_converted.get(
                                    'Sunday') and mp_week_converted.get('Sunday').get(
                                    'breakfast') else f"No breakfast found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Sunday').get('lunch').get('img_url')}" if mp_week_converted.get(
                                    'Sunday') and mp_week_converted.get('Sunday').get(
                                    'lunch') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Sunday').get('lunch').get('title')}" if mp_week_converted.get(
                                    'Sunday') and mp_week_converted.get('Sunday').get('lunch') else f"No lunch found..."
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "image",
                                "image_url": f"{mp_week_converted.get('Sunday').get('dinner').get('img_url')}" if mp_week_converted.get(
                                    'Sunday') and mp_week_converted.get('Sunday').get(
                                    'dinner') else EMPTY_DINNER_PLATE_IMG,
                                "alt_text": "Meal Image"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"{mp_week_converted.get('Sunday').get('dinner').get('title')}" if mp_week_converted.get(
                                    'Sunday') and mp_week_converted.get('Sunday').get(
                                    'dinner') else f"No dinner found..."
                            }
                        ]
                    },
                    block_divider
                ]
            }
        )

    except Exception as e:
        g_logger.error(f"Error publishing meal plan pane on home tab: {e}")


# Publish meal plan DETAIL pane on home view
def publish_meal_plan_detail_home_view(client, user, date: str):
    try:
        # Loading screen
        client.views_publish(
            user_id=user,
            view={
                "type": "home",
                "callback_id": "home_view_meal_plans_detail_loading",
                "blocks": [
                    welcome_home_block,
                    block_divider,
                    home_view_main_nav_buttons,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Loading meal plan details...*"
                        }
                    }
                ]
            }
        )

        meal_plan_day_response = get_meal_plan_for_day(date)
        date_formatted = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%A %B %d, %Y")

        blocks_json = [
            welcome_home_block,
            block_divider,
            home_view_main_nav_buttons,
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{date_formatted}"
                }
            },
            block_divider
        ]

        if meal_plan_day_response.get("items"):
            nutrition_summary = meal_plan_day_response.get("nutritionSummary").get("nutrients")

            for meal in meal_plan_day_response.get("items"):
                item_id = meal.get("id")
                meal_id = meal.get("value").get("id")
                full_recipe = get_recipe_by_id(meal_id)

                if meal.get("slot") == 1:
                    meal_time = "Breakfast"
                elif meal.get("slot") == 2:
                    meal_time = "Lunch"
                elif meal.get("slot") == 3:
                    meal_time = "Dinner"
                else:
                    meal_time = "Other"

                meal_img = full_recipe.get('image')

                if full_recipe.get("summary"):
                    summary = full_recipe.get("summary").replace('<b>', '*').replace('</b>', '*')
                    summary = re.sub(r'<.*?', '', summary)
                    summary = f"{summary[:180]}..."
                else:
                    summary = "No summary found..."

                vegan = "*V*" if full_recipe.get('vegan') else ""
                vegetarian = "*Veg*" if full_recipe.get('vegetarian') else ""
                gluten_free = "*GF*" if full_recipe.get('glutenFree') else ""
                dairy_free = "*DF*" if full_recipe.get('dairyFree') else ""

                category_str = "None Found" if not vegan and not vegetarian and not gluten_free and not dairy_free else f"{vegan} {vegetarian} {gluten_free} {dairy_free}"

                blocks_json.append(
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{meal_time}"
                        }
                    }
                )
                blocks_json.append(block_divider)
                blocks_json.append(
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{full_recipe.get('title')}"
                        }
                    }
                )
                blocks_json.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{summary}\nReady In: {full_recipe.get('readyInMinutes')} minutes | Servings:"
                                    f" {full_recipe.get('servings')}\t{category_str}"
                        },
                        "accessory": {
                            "type": "image",
                            "image_url": meal_img,
                            "alt_text": f"Meal Img"
                        },
                        "block_id": f"daily_meal_plan_item_{str(meal_id)}_{full_recipe.get('title')}_{full_recipe.get('servings')}"
                    }
                )
                blocks_json.append(
                    {
                        "type": "actions",
                        "block_id": f"daily_meal_plan_view_source_{str(meal_id)}_action",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "View Source"
                                },
                                "value": str(meal_id),
                                "action_id": "daily_meal_plan_view_source",
                                "url": full_recipe.get('sourceUrl')
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Remove from meal plan"
                                },
                                "value": f"{str(item_id)}_{date}",
                                "action_id": "delete_item_from_mp"
                            }
                        ]
                    }
                )

            blocks_json.append(block_divider)
            blocks_json.append(
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"Combined Nutrients"
                    }
                }
            )
            blocks_json.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Calories*: {next((x['amount'] for x in nutrition_summary if x['name'] == 'Calories'), 'Not found')},"
                                f" *Protein*: {next((x['amount'] for x in nutrition_summary if x['name'] == 'Protein'), 'Not found')},"
                                f" *Fat*: {next((x['amount'] for x in nutrition_summary if x['name'] == 'Fat'), 'Not found')},"
                                f" *Carbs*: {next((x['amount'] for x in nutrition_summary if x['name'] == 'Carbohydrates'), 'Not found')}\n"
                    }
                }
            )

        else:
            blocks_json.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"No meals planned...\n\nUse the `/recipes` command to find new meals and recipes!"
                    }
                }
            )

        # Publish meal plan detail view
        client.views_publish(
            user_id=user,
            view={
                "type": "home",
                "callback_id": "home_view_meal_plans_detail",
                "blocks": blocks_json
            }
        )


    except Exception as e:
        g_logger.error(f"Error publishing meal plan detail on home tab: {e}")


# Publish recipe pane on home view
def publish_recipe_home_view(client, user):
    try:

        client.views_publish(
            user_id=user,
            view={
                "type": "home",
                "callback_id": "home_view",
                "blocks": [
                    welcome_home_block,
                    block_divider,
                    home_view_main_nav_buttons,
                    block_divider,
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Recipes"
                        }
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Something Here"
                        }
                    },
                    {
                        "type": "image",
                        "image_url": SALAD_BOWL_IMG,
                        "alt_text": "Recipe pane image"
                    },
                    block_divider
                ]
            }
        )

    except Exception as e:
        g_logger.error(f"Error publishing recipe pane on home tab: {e}")


@app.event("app_home_opened")
def update_home_tab(client, event, logger):
    publish_main_home_view(client, event['user'])


@app.event("message")
def handle_message_events(say, body, logger):
    msg_incoming = body.get("event").get("blocks")[0].get("elements")[0].get("elements")[0].get("text").lower()
    g_logger.debug(f"Received msg: {msg_incoming}")
    if msg_incoming is not None and ("command" in msg_incoming or "help" in msg_incoming or "guide" in msg_incoming):
        say("Yeah...better try `/nickbot guide` to get more info...")
    elif msg_incoming is not None and "hello" in msg_incoming:
        say("Hey there! How's your day so far?  Mine's ok but I'm stuck indoors.")
    elif msg_incoming is not None and "joke" in msg_incoming:
        say("Joke? Look in the mirror.")
    elif msg_incoming is not None and "recipe" in msg_incoming:
        say("Looking for a recipe? Check out the recipe commands by typing `/nickbot guide`")
    elif msg_incoming is not None and (
            "shopping" in msg_incoming or "grocery" in msg_incoming or "groceries" in msg_incoming):
        say("Need to do some shopping? Check out the shoplist commands by typing `/nickbot guide`")
    else:
        say("Are you talking to me?  I was asleep.")


# # # # # # # # # # # # # # # # # #
# #    LISTENING TO COMMANDS    # #
# # # # # # # # # # # # # # # # # #

@app.command("/nickbot")
def show_guide(ack, say, command):
    # Acknowledge command request
    ack()

    say({
        "text": "NickBot Guide",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*These are the available NickBot commands:*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "`/nickbot` or `/nickbot guide` Show the guide"
                }
            },
            block_divider,
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "`/recipe random` Get a random recipe\n`/recipe ingredients` Search recipes using the "
                            "ingredients you have\n`/recipe search` Search for recipes with any phrase"
                }
            },
            block_divider,
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "`/shoplist list` List all items in shopping list\n`/shoplist sort`"
                            " Attempt to analyze items and sort by aisle\n`/shoplist add` Add an item to your "
                            "shopping list\n`/shoplist delete` Remove a specific item from your shopping list\n"
                            "`/shoplist empty` Remove all items from your shopping list"
                }
            },
            block_divider,
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "`/mealplan generate` Generate a new meal plan"
                }
            },
            block_divider,
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "`/nutrients` Search nutrient info for an ingredient"
                }
            }
        ]
    })


@app.command("/recipe")
def recipe_process(ack, say, command, logger):
    # Acknowledge command request
    ack()

    recipe_cmd = command['text'].split(' ', 1)[0]
    g_logger.debug(f"\nReceived cmd /recipe {command['text']}.\n")

    # RANDOM
    if recipe_cmd.startswith("random"):
        random_response = get_random_recipe()
        recipe = random_response.get("recipes")[0]
        title = recipe.get("title")
        img_url = recipe.get("image", "No image found")

        if recipe.get("summary"):
            summary = recipe.get("summary").replace('<b>', '*').replace('</b>', '*')
            summary = re.sub(r'<.*?', '', summary)
            summary = f"{summary[:350]}..."
        else:
            summary = "No summary found..."

        source_url = recipe.get("sourceUrl")
        extended_ingred_list = []
        for ingred in recipe.get("extendedIngredients"):
            extended_ingred_list.append(ingred.get("original"))
        ingreds_joined = ", ".join(extended_ingred_list)
        ready_in_mins = recipe.get("readyInMinutes")
        recipe_id = recipe.get("id")

        say({
            "text": "Random recipe",
            "blocks": [
                block_divider,
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{title}"
                    }
                },
                block_divider,
                {
                    "type": "image",
                    "title": {
                        "type": "plain_text",
                        "text": f"Image of {title}"
                    },
                    "image_url": img_url,
                    "alt_text": f"Image of {title}"
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"    {summary}"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Ingredients*: \n{ingreds_joined}\n\n*Ready in*: {ready_in_mins} mins"
                    }
                },
                {
                    "type": "actions",
                    "block_id": "random_recipe_action",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Add all to shopping list"
                            },
                            "value": str(recipe_id),
                            "action_id": "random_recipe_add_all_to_shop_list"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Show instructions"
                            },
                            "value": str(recipe_id),
                            "action_id": "recipe_show_instructions"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View Source"
                            },
                            "value": str(recipe_id),
                            "action_id": "random_recipe_view_source",
                            "url": source_url
                        }
                    ]
                },
                block_divider
            ]
        })

    # INGREDIENTS
    elif recipe_cmd.startswith("ingredients"):
        say({
            "text": "Ingredient Multi Select",
            "blocks": [
                block_divider,
                {
                    "type": "section",
                    "block_id": "ingred_multi_select",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Select your ingredients:"
                    },
                    "accessory": {
                        "action_id": "ingred_multi_select",
                        "type": "multi_external_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "What's in your fridge?"
                        },
                        "min_query_length": 1
                    }
                }
            ]
        })

    # SEARCH
    elif recipe_cmd.startswith("search"):
        search_response = search_all_recipes(command['text'][6:])
        total_results = search_response.get("totalResults")

        if total_results < 1:
            say("Sorry, no results were found!  You're too creative for me!")
        else:
            first_result = search_response.get("results")[0]
            recipe_id = first_result.get("id")
            recipe = get_recipe_by_id(recipe_id)
            title = recipe.get("title")
            img_url = recipe.get("image", "No image found")

            if recipe.get("summary"):
                summary = recipe.get("summary").replace('<b>', '*').replace('</b>', '*')
                summary = re.sub(r'<.*?', '', summary)
                summary = f"{summary[:350]}..."
            else:
                summary = "No summary found..."

            source_url = recipe.get("sourceUrl")
            extended_ingred_list = []
            for ingred in recipe.get("extendedIngredients"):
                extended_ingred_list.append(ingred.get("original"))
            ingreds_joined = ", ".join(extended_ingred_list)
            ready_in_mins = recipe.get("readyInMinutes")
            recipe_id = recipe.get("id")

            say({
                "text": "Top Recipe Found",
                "blocks": [
                    block_divider,
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{title}"
                        }
                    },
                    block_divider,
                    {
                        "type": "image",
                        "title": {
                            "type": "plain_text",
                            "text": f"Image of {title}"
                        },
                        "image_url": img_url,
                        "alt_text": f"Image of {title}"
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Summary*: {summary}"
                        }
                    },
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Ingredients*: {ingreds_joined}\n\n*Ready in*: {ready_in_mins} mins"
                        }
                    },
                    {
                        "type": "actions",
                        "block_id": "random_recipe_action",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Add all to shopping list"
                                },
                                "value": str(recipe_id),
                                "action_id": "random_recipe_add_all_to_shop_list"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Show instructions"
                                },
                                "value": str(recipe_id),
                                "action_id": "recipe_show_instructions"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "View Source"
                                },
                                "value": str(recipe_id),
                                "action_id": "random_recipe_view_source",
                                "url": source_url
                            }
                        ]
                    },
                    block_divider
                ]
            })

    else:
        say(SAY_INVALID_CMD)


# @app.command("/shoplist")
def shoplist_process(ack, say, command, logger):
    # Acknowledge command request
    ack()

    shoplist_cmd = command['text'].split(' ', 1)[0]
    g_logger.debug(f"\nReceived cmd /shoplist {command['text']}.\n")

    if shoplist_cmd.startswith("list"):
        list_response = list_items_in_shopping_list()
        items = []
        if len(list_response.get("aisles")) > 0:
            for aisle in list_response.get("aisles"):
                for item in aisle.get("items"):
                    items.append(f"{item.get('name')} ({item.get('measures').get('original').get('amount')}"
                                 f" {item.get('measures').get('original').get('unit')})")

            spaced_list = '\n'.join(items)
            g_logger.debug(f"Current shopping list: {spaced_list}")

            say({
                "blocks": [
                    block_divider,
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Your Shopping List ({len(items)} items)"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{spaced_list}"
                        },
                        "accessory": {
                            "type": "image",
                            "image_url": EMPTY_SHOPPING_CART_IMG,
                            "alt_text": f"Shopping Cart Icon"
                        }
                    }
                ]
            })
        else:
            say(SAY_SHOP_LIST_EMPTY)

    elif shoplist_cmd.startswith("sort"):
        list_response = list_items_in_shopping_list()
        if len(list_response.get("aisles")) > 0:
            say(create_sorted_aisles_display_block(list_response.get("aisles")))
        else:
            say(SAY_SHOP_LIST_EMPTY)

    elif shoplist_cmd.startswith("add"):
        item = command['text'][4:]
        add_response = add_item_to_shopping_list(item, True)
        if len(add_response) > 0:
            say({
                "blocks": [
                    block_divider,
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Added *{item}* to shopping list"
                        }
                    }
                ]
            })
        else:
            say(f"Oh no!  There was an issue adding {item} to your shopping list.")

    elif shoplist_cmd.startswith("delete"):
        if command['text'] == "delete":
            say("You didn't specify an item to delete... try `/shoplist delete ITEM_HERE`")
        else:
            item_del = command['text'][7:]
            del_response = delete_item_from_shopping_list(item_del)
            if del_response.get("not_found"):
                say(f"Uh oh!  Could not find or delete {item_del} from your shopping list")
            else:
                say(f"Deleted {item_del} from your shopping list")

    elif shoplist_cmd.startswith("empty"):
        say("Emptying shopping list...")
        empty_shopping_list()
        say("Shopping list is now empty")

    else:
        say(SAY_INVALID_CMD)


# Lazy listener for /shoplist command
app.command("/shoplist")(
    ack=lazy_listener_ack,
    lazy=[shoplist_process]
)


@app.command("/mealplan")
def mealplan_process(ack, say, command):
    # Acknowledge command request
    ack()

    try:
        mealplan_cmd = command['text'].split(' ', 1)[0]
    except KeyError as e:
        g_logger.debug(f"Mealplan command key error: {e}")
        say(SAY_INVALID_CMD)
        return
    g_logger.debug(f"\nReceived cmd /mealplan {command['text']}.\n")

    if mealplan_cmd.startswith("generate"):
        say({
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Let's generate a meal plan!"
                    }
                },
                {  # Day or Week picker
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Meal plan for one day or an entire week?"
                    },
                    "accessory": {
                        "type": "static_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Day or Week",
                            "emoji": True
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Day",
                                    "emoji": True
                                },
                                "value": "Day"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Week",
                                    "emoji": True
                                },
                                "value": "Week"
                            }
                        ],
                        "action_id": "static_select_day_week-action"
                    }
                },
                {  # Diet picker
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Does this plan need to adhere to a diet?"
                    },
                    "accessory": {
                        "type": "static_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select an item",
                            "emoji": True
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "None",
                                    "emoji": True
                                },
                                "value": "None"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Gluten Free",
                                    "emoji": True
                                },
                                "value": "Gluten Free"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Ketogenic",
                                    "emoji": True
                                },
                                "value": "Ketogenic"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Vegetarian",
                                    "emoji": True
                                },
                                "value": "Vegetarian"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Vegan",
                                    "emoji": True
                                },
                                "value": "Vegan"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Lacto-Vegetarian",
                                    "emoji": True
                                },
                                "value": "Lacto-Vegetarian"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Ovo-Vegetarian",
                                    "emoji": True
                                },
                                "value": "Ovo-Vegetarian"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Paleo",
                                    "emoji": True
                                },
                                "value": "Paleo"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Pescetarian",
                                    "emoji": True
                                },
                                "value": "Pescetarian"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Primal",
                                    "emoji": True
                                },
                                "value": "Primal"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Low FODMAP",
                                    "emoji": True
                                },
                                "value": "Low FODMAP"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Whole30",
                                    "emoji": True
                                },
                                "value": "Whole30"
                            }

                        ],
                        "action_id": "static_select_diet-action"
                    }
                },
                {  # Calorie Picker
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "What is the caloric target for one day?"
                    },
                    "accessory": {
                        "type": "static_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select an option",
                            "emoji": True
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "0",
                                    "emoji": True
                                },
                                "value": "0"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "250",
                                    "emoji": True
                                },
                                "value": "250"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "500",
                                    "emoji": True
                                },
                                "value": "500"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "750",
                                    "emoji": True
                                },
                                "value": "750"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "1000",
                                    "emoji": True
                                },
                                "value": "1000"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "1250",
                                    "emoji": True
                                },
                                "value": "1250"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "1500",
                                    "emoji": True
                                },
                                "value": "1500"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "1750",
                                    "emoji": True
                                },
                                "value": "1750"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "2000",
                                    "emoji": True
                                },
                                "value": "2000"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "2250",
                                    "emoji": True
                                },
                                "value": "2250"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "2500",
                                    "emoji": True
                                },
                                "value": "2500"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "2750",
                                    "emoji": True
                                },
                                "value": "2750"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "3000",
                                    "emoji": True
                                },
                                "value": "3000"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "3250",
                                    "emoji": True
                                },
                                "value": "3250"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "3500",
                                    "emoji": True
                                },
                                "value": "3500"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "4000",
                                    "emoji": True
                                },
                                "value": "4000"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "4500",
                                    "emoji": True
                                },
                                "value": "4500"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "5000",
                                    "emoji": True
                                },
                                "value": "5000"
                            }
                        ],
                        "action_id": "static_select_calorie-action"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Generate Meal Plan",
                                "emoji": True
                            },
                            "value": "click_me_generate_plan",
                            "action_id": "actionId-generate_plan",
                            "style": "primary"
                        }
                    ]
                }
            ]
        })
        # generate_response = generate_meal_plan(time_frame, target_calories, diet, exclude)
    else:
        say(SAY_INVALID_CMD)


@app.command("/nutrients")
def nutrients_process(ack, say, body, command, client):
    # Acknowledge command request
    ack()

    client.views_open(
        # Pass a valid trigger_id within 3 seconds of receiving it
        trigger_id=body["trigger_id"],
        # View payload
        view={
            "type": "modal",
            # View identifier
            "callback_id": "modal_nutrients",
            "title": {"type": "plain_text", "text": "Search Nutrient Info"},
            "blocks": [
                block_divider,
                {
                    "type": "section",
                    "block_id": "ingred_nutrient_select",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Find an ingredient to get nutrient info:"
                    },
                    "accessory": {
                        "action_id": "ingred_nutrient_select",
                        "type": "external_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Search ingredients"
                        },
                        "min_query_length": 1
                    }
                }
            ]
        }
    )


# # # # # # # # # # # # # # # # # #
# #    LISTENING TO ACTIONS     # #
# # # # # # # # # # # # # # # # # #


@app.action("meal_plan_date_picker")
def meal_plan_date_picker(ack, say, body, logger):
    ack()
    g_logger.debug(f"Meal plan date picker - body: {body}")

    # Selected date in format yyyy-mm-dd
    selected_date = body.get("state").get("values").get("meal_plan_date_picker_section").get(
        "meal_plan_date_picker").get("selected_date")
    blocks = body.get("message").get("blocks")
    meals_list = []

    for block in blocks:
        if block.get("block_id").startswith('daily_meal_plan_item_'):
            block_id_parsed = block.get("block_id").split('_')
            meal_id = block_id_parsed[4]
            meal_title = block_id_parsed[5]
            meal_servings = block_id_parsed[6]
            meals_list.append(
                {
                    "id": int(meal_id),
                    "servings": int(meal_servings),
                    "title": meal_title,
                    "imageType": "jpg"
                }
            )

    response = add_daily_meal_plan_to_calendar_day(selected_date, "RECIPE", meals_list)
    if response.get("status") == "success":
        say(f"Meal plan successfully added on *{selected_date}*!")
    else:
        say(f"Uh oh!  There was a problem adding your meal plan...")


@app.action("random_recipe_view_source")
def random_recipe_view_source(ack, body, logger):
    ack()
    g_logger.debug(f"Random recipe view source - body: {body}")


@app.action("daily_meal_plan_view_source")
def daily_meal_plan_view_source(ack, body, logger):
    ack()
    g_logger.debug(f"Dail meal plan view source - body: {body}")


@app.action("recipe_show_instructions")
def open_instructions_modal(ack, body, client, logger):
    ack()
    g_logger.debug(f"Recipe show instructions modal body: {body}")

    recipe_id = body.get("actions")[0].get("value")
    recipe = get_recipe_by_id(recipe_id)
    # instructions = re.sub(r'<.*?>', '', recipe.get("instructions", ""))
    analyzed_instructions = recipe.get("analyzedInstructions", "")
    numbered_instructions = ''
    title = recipe.get("title")

    for instruction in analyzed_instructions:
        for step in instruction.get("steps"):
            numbered_instructions += f"*{step.get('number')})* {step.get('step')}\n"

    client.views_open(
        # Pass a valid trigger_id within 3 seconds of receiving it
        trigger_id=body["trigger_id"],
        # View payload
        view={
            "type": "modal",
            # View identifier
            "callback_id": "view_1",
            "title": {"type": "plain_text", "text": "Recipe Instructions"},
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": numbered_instructions}
                }
            ]
        }
    )


@app.action("ingred_nutrient_select")
def ingred_nutrient_select(ack, say, body, logger, client):
    ack()

    g_logger.debug(f"Ingredient nutrient select body: {body}")

    ingred_id = body.get("actions")[0].get("selected_option").get("value")
    ingred_name = body.get("actions")[0].get("selected_option").get("text").get("text")

    g_logger.debug(f"\nSelected {ingred_name} with id {ingred_id}.")

    ingredient_response = get_ingredient_info_by_id(ingred_id)
    # say(display_nutrition_details_for_ingredient(ingredient_response))

    blocks = [
        block_divider,
        {
            "type": "section",
            "block_id": "ingred_nutrient_select",
            "text": {
                "type": "mrkdwn",
                "text": "Find an ingredient to get nutrient info:"
            },
            "accessory": {
                "action_id": "ingred_nutrient_select",
                "type": "external_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Search ingredients"
                },
                "min_query_length": 1
            }
        }
    ]

    blocks = append_nutrient_info_to_block_list(blocks, ingredient_response)

    client.views_update(
        view_id=body["view"]["id"],
        hash=body["view"]["hash"],
        view={
            "type": "modal",
            # View identifier
            "callback_id": "view_show_nutrient_info",
            "title": {"type": "plain_text", "text": "Search Nutrition Info"},
            "blocks": blocks
        }
    )


# Button press to add searched item to shopping list from home screen
@app.action("home_shop_list_add_item_action")
def home_shop_list_add_item_action(ack, say, body, logger, client, event):
    ack()
    g_logger.debug(f"Home page - ingredient select body: {body}")

    state_vals = body.get("view").get("state").get("values")
    selected_opt = state_vals.get("home_shop_list_actions_block").get("home_shop_list_search_ingred_action").get(
        "selected_option")

    if selected_opt:
        selected_ingred_name = selected_opt.get("text").get("text")

        add_item_to_shopping_list(selected_ingred_name, True)

        # Refresh home view with shopping list
        g_logger.debug(f"Client: {client}")  # not null
        g_logger.debug(f"Event: {event}")  # null
        publish_main_home_view(client, body.get("user").get("id"))

        # Need channel id to post msg in chat
        """say({
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Added *{selected_ingred_name}* to shopping list"
                    }
                }
            ]
        })"""
    else:
        g_logger.debug("No ingredient was selected to add!")
        # Modal to say nothing was selected? or just SAY to channel


# Button press to DELETE searched item from shopping list from home screen
@app.action("home_shop_list_delete_item_action")
def home_shop_list_delete_item_action(ack, say, body, logger, client, event):
    ack()
    g_logger.debug(f"Home page - ingredient select body: {body}")

    state_vals = body.get("view").get("state").get("values")
    selected_opt = state_vals.get("home_shop_list_actions_block").get("home_shop_list_search_ingred_action").get(
        "selected_option")

    if selected_opt:
        selected_ingred_name = selected_opt.get("text").get("text")

        delete_item_from_shopping_list(selected_ingred_name)

        # Refresh home view with shopping list
        g_logger.debug(f"Client: {client}")  # not null
        g_logger.debug(f"Event: {event}")  # null
        publish_main_home_view(client, body.get("user").get("id"))
    else:
        g_logger.debug("No ingredient was selected to delete!")
        # Modal to say nothing was selected? or just SAY to channel


@app.action("ingred_multi_select")
def ingredients_selected_action(ack, say, body, logger):
    ack()

    g_logger.debug(f"Ingredient multi-select body: {body}")
    search_list = []

    say("Searching for recipes with your ingredients...")

    for option in body.get("actions")[0].get("selected_options"):
        search_list.append(option.get("value"))

    search_response = search_all_recipes_by_ingredients(search_list)
    g_logger.debug(f"Search recipes by ingredients response: {search_response}")

    if len(search_response) < 1:
        say("Oh no!  We couldn't find any recipes with that ingredient list!")
    else:
        blocks = {
            "text": "Ingredients Recipe Results",
            "blocks": []
        }
        blocks.get("blocks").append(block_divider)

        for recipe in search_response:
            title = recipe.get("title")
            recipe_id = recipe.get("id")
            img_url = recipe.get("image", "No image found")
            extended_used_ingred_list, extended_missing_ingred_list = [], []
            for ingred in recipe.get("usedIngredients"):
                extended_used_ingred_list.append(ingred.get("original"))
            for ingred in recipe.get("missedIngredients"):
                extended_missing_ingred_list.append(ingred.get("original"))
            used_ingreds_joined = ", ".join(extended_used_ingred_list) if len(
                extended_used_ingred_list) > 0 else "No used ingredients..."
            missing_ingreds_joined = ", ".join(extended_missing_ingred_list) if len(
                extended_missing_ingred_list) > 0 else "No missed ingredients..."
            blocks.get("blocks").append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{title}*\n*Used Ingredients*: {used_ingreds_joined}\n*Missing "
                                f"Ingredients*: {missing_ingreds_joined}"
                    },
                    "accessory": {
                        "type": "image",
                        "image_url": img_url,
                        "alt_text": f"Img of {title}"
                    }
                }
            )
            blocks.get("blocks").append(
                {
                    "type": "actions",
                    "block_id": f"ingred_results_{recipe_id}",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View full recipe"
                            },
                            "value": str(recipe_id),
                            "action_id": "ingred_recipe_show_full_recipe"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Add missing to shopping list"
                            },
                            "value": missing_ingreds_joined,
                            "action_id": "ingred_recipe_add_missing_to_shop_list"
                        }
                    ]
                }
            )
            blocks.get("blocks").append(block_divider)

        say(blocks)


@app.action("static_select_day_week-action")
def static_select_day_week(ack, body, logger):
    ack()
    g_logger.debug(f"Meal plan day picker body: {body}")

    # Get timeFrame from body
    time_frame = body.get("actions")[0].get("selected_option").get("value")
    g_logger.debug(f"Meal plan day picker: {time_frame}")

    global GENERATE_MEAL_PLAN_OPTIONS
    GENERATE_MEAL_PLAN_OPTIONS['timeFrame'] = time_frame


@app.action("static_select_diet-action")
def static_select_diet(ack, body, logger):
    ack()
    g_logger.debug(f"Meal plan diet picker body: {body}")

    # Get diet from body
    diet = body.get("actions")[0].get("selected_option").get("value")
    g_logger.debug(f"Meal plan diet picker: {diet}")

    global GENERATE_MEAL_PLAN_OPTIONS
    GENERATE_MEAL_PLAN_OPTIONS['diet'] = diet if diet != "None" else ""


@app.action("static_select_calorie-action")
def static_select_calorie(ack, body, logger):
    ack()
    g_logger.debug(f"Meal plan calorie picker body: {body}")

    # Get calories from body
    calories = body.get("actions")[0].get("selected_option").get("value")
    g_logger.debug(f"Meal plan calorie picker: {calories}")

    global GENERATE_MEAL_PLAN_OPTIONS
    GENERATE_MEAL_PLAN_OPTIONS['targetCalories'] = calories


@app.action("actionId-generate_plan")
def generate_meal_plan_action(ack, say, body, logger):
    ack()

    g_logger.debug(f"Generate meal plan body: {body}")

    global GENERATE_MEAL_PLAN_OPTIONS

    generate_meal_plan_response = generate_meal_plan(GENERATE_MEAL_PLAN_OPTIONS['timeFrame'],
                                                     GENERATE_MEAL_PLAN_OPTIONS['targetCalories'],
                                                     GENERATE_MEAL_PLAN_OPTIONS['diet'], "")

    if generate_meal_plan_response.get("week"):
        mon_plan = generate_meal_plan_response.get("week").get("monday")
        tues_plan = generate_meal_plan_response.get("week").get("tuesday")
        wed_plan = generate_meal_plan_response.get("week").get("wednesday")
        thurs_plan = generate_meal_plan_response.get("week").get("thursday")
        fri_plan = generate_meal_plan_response.get("week").get("friday")
        sat_plan = generate_meal_plan_response.get("week").get("saturday")
        sun_plan = generate_meal_plan_response.get("week").get("sunday")

        say({
            "blocks": [
                block_divider,
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Your 7 day meal plan"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Monday:*\n {mon_plan.get('meals')[0].get('title')}, {mon_plan.get('meals')[1].get('title')},"
                                f" {mon_plan.get('meals')[2].get('title')}\n*Calories*: {mon_plan.get('nutrients').get('calories')}"
                                f" *Protein*: {mon_plan.get('nutrients').get('protein')} *Fat*: {mon_plan.get('nutrients').get('fat')}"
                                f" *Carbs*: {mon_plan.get('nutrients').get('carbohydrates')}"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Tuesday:*\n {tues_plan.get('meals')[0].get('title')}, {tues_plan.get('meals')[1].get('title')},"
                                f" {tues_plan.get('meals')[2].get('title')}\n*Calories*: {tues_plan.get('nutrients').get('calories')}"
                                f" *Protein*: {tues_plan.get('nutrients').get('protein')} *Fat*: {tues_plan.get('nutrients').get('fat')}"
                                f" *Carbs*: {tues_plan.get('nutrients').get('carbohydrates')}"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Wednesday:*\n {wed_plan.get('meals')[0].get('title')}, {wed_plan.get('meals')[1].get('title')},"
                                f" {wed_plan.get('meals')[2].get('title')}\n*Calories*: {wed_plan.get('nutrients').get('calories')}"
                                f" *Protein*: {wed_plan.get('nutrients').get('protein')} *Fat*: {wed_plan.get('nutrients').get('fat')}"
                                f" *Carbs*: {wed_plan.get('nutrients').get('carbohydrates')}"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Thursday:*\n {thurs_plan.get('meals')[0].get('title')}, {thurs_plan.get('meals')[1].get('title')},"
                                f" {thurs_plan.get('meals')[2].get('title')}\n*Calories*: {thurs_plan.get('nutrients').get('calories')}"
                                f" *Protein*: {thurs_plan.get('nutrients').get('protein')} *Fat*: {thurs_plan.get('nutrients').get('fat')}"
                                f" *Carbs*: {thurs_plan.get('nutrients').get('carbohydrates')}"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Friday:*\n {fri_plan.get('meals')[0].get('title')}, {fri_plan.get('meals')[1].get('title')},"
                                f" {fri_plan.get('meals')[2].get('title')}\n*Calories*: {fri_plan.get('nutrients').get('calories')}"
                                f" *Protein*: {fri_plan.get('nutrients').get('protein')} *Fat*: {fri_plan.get('nutrients').get('fat')}"
                                f" *Carbs*: {fri_plan.get('nutrients').get('carbohydrates')}"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Saturday:*\n {sat_plan.get('meals')[0].get('title')}, {sat_plan.get('meals')[1].get('title')},"
                                f" {sat_plan.get('meals')[2].get('title')}\n*Calories*: {sat_plan.get('nutrients').get('calories')}"
                                f" *Protein*: {sat_plan.get('nutrients').get('protein')} *Fat*: {sat_plan.get('nutrients').get('fat')}"
                                f" *Carbs*: {sat_plan.get('nutrients').get('carbohydrates')}"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Sunday:*\n {sun_plan.get('meals')[0].get('title')}, {sun_plan.get('meals')[1].get('title')},"
                                f" {sun_plan.get('meals')[2].get('title')}\n*Calories*: {sun_plan.get('nutrients').get('calories')}"
                                f" *Protein*: {sun_plan.get('nutrients').get('protein')} *Fat*: {sun_plan.get('nutrients').get('fat')}"
                                f" *Carbs*: {sun_plan.get('nutrients').get('carbohydrates')}"
                    }
                }
            ]
        })

    else:
        say(display_daily_meal_plan_and_nutrients(generate_meal_plan_response))


# Add all ingredients from random recipe to shopping list
@app.action("random_recipe_add_all_to_shop_list")
def random_recipe_add_all_to_shop_list(ack, say, body, logger):
    ack()

    g_logger.debug(f"Random recipe add all ingredients to shopping list - body: {body}")

    recipe_id = body.get("actions")[0].get("value")

    say("Yay!  Someone is hungry today.  Adding items now...")
    add_response = add_recipe_ingredients_to_shop_list(recipe_id)
    total_added = add_response.get("total_added")

    if add_response:
        say({
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Awesome!* {total_added} items were added to your shopping list"
                    }
                }
            ]
        })
    else:
        say("Uh oh!  Something went wrong...")


# View full recipe details from button press in '/recipe ingredients' results
@app.action("ingred_recipe_show_full_recipe")
def show_full_recipe_from_results_list(ack, say, body, logger):
    ack()

    g_logger.debug(f"Show full recipe body: {body}")

    recipe_id = body.get("actions")[0].get("value")
    recipe = get_recipe_by_id(recipe_id)

    # recipe = recipe_response.get("recipes")[0]
    title = recipe.get("title")
    img_url = recipe.get("image", "No image found")

    if recipe.get("summary"):
        summary = recipe.get("summary").replace('<b>', '*').replace('</b>', '*')
        summary = re.sub(r'<.*?', '', summary)
        summary = f"{summary[:350]}..."
    else:
        summary = "No summary found..."

    source_url = recipe.get("sourceUrl")
    extended_ingred_list = []
    for ingred in recipe.get("extendedIngredients"):
        extended_ingred_list.append(ingred.get("original"))
    ingreds_joined = ", ".join(extended_ingred_list)
    ready_in_mins = recipe.get("readyInMinutes")
    recipe_id = recipe.get("id")

    say(
        say({
            "text": "Random recipe",
            "blocks": [
                block_divider,
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{title}"
                    }
                },
                block_divider,
                {
                    "type": "image",
                    "title": {
                        "type": "plain_text",
                        "text": f"Image of {title}"
                    },
                    "image_url": img_url,
                    "alt_text": f"Image of {title}"
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"    {summary}"
                    }
                },
                block_divider,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Ingredients*: \n{ingreds_joined}\n\n*Ready in*: {ready_in_mins} mins"
                    }
                },
                {
                    "type": "actions",
                    "block_id": "ingred_recipe_action",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Add all to shopping list"
                            },
                            "value": str(recipe_id),
                            "action_id": "random_recipe_add_all_to_shop_list"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Show instructions"
                            },
                            "value": str(recipe_id),
                            "action_id": "recipe_show_instructions"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View Source"
                            },
                            "value": str(recipe_id),
                            "action_id": "random_recipe_view_source",
                            "url": source_url
                        }
                    ]
                },
                block_divider
            ]
        })
    )


@app.action("ingred_recipe_add_missing_to_shop_list")
def add_missing_ingredients_to_shop_list(ack, say, body, logger):
    ack()
    g_logger.debug(f"Add missing ingredients to shopping list body: {body}")

    missing_ingredients = body.get("actions")[0].get("value").split(", ")
    for ingred in missing_ingredients:
        add_item_to_shopping_list(ingred, True)
    say(f"Added *{len(missing_ingredients)} items* to your shopping list")


# Empty shopping list from Home screen button press and publish view
def home_shop_list_empty_action(ack, say, body, logger, client):
    g_logger.debug("Got to Lazy empty shopping list!")
    empty_shopping_list()

    publish_main_home_view(client, body.get("user").get("id"))


# -- Lazy listener --
# Empty shopping list from Home screen button press
app.action('home_shop_list_empty_action')(
    ack=lazy_listener_ack,
    lazy=[home_shop_list_empty_action]
)


# Action when user selects an ingredient under shopping list on home screen
@app.action('home_shop_list_search_ingred_action')
def home_shop_list_search_ingred_action(ack, say, body, logger):
    ack()


# Button press on home view to show Meal Plans
def home_view_meal_plans_action(ack, say, body, logger, client):
    publish_meal_plan_home_view(client, body.get("user").get("id"))


# Lazy listener for Meal Plans Calendar button press
app.action('home_view_meal_plans_action')(
    ack=lazy_listener_ack,
    lazy=[home_view_meal_plans_action]
)


# Overflow menu press to view meal plan details for a specific day
@app.action("mp_view_day")
def mp_view_day(ack, say, body, logger, client):
    ack()

    # Date in the format yyyy-mm-dd
    date = body.get("actions")[0].get("selected_option").get("value")

    publish_meal_plan_detail_home_view(client, body.get("user").get("id"), date)


# Button press on home view to show shopping list
@app.action("home_view_shop_list_action")
def home_view_shop_list_action(ack, say, body, logger, client):
    ack()

    publish_main_home_view(client, body.get("user").get("id"))


# Button press on home view to show sorted shopping list
@app.action("home_shop_list_sort_action")
def home_shop_list_sort_action(ack, say, body, logger, client):
    ack()

    publish_main_home_view_sorted(client, body.get("user").get("id"))


# Button press on home view to show unsorted shopping list
@app.action("home_shop_list_unsort_action")
def home_shop_list_unsort_action(ack, say, body, logger, client):
    ack()

    publish_main_home_view(client, body.get("user").get("id"))


# Button press on home view to show recipes
@app.action("home_view_recipes_action")
def home_view_recipes_action(ack, say, body, logger, client):
    ack()

    publish_recipe_home_view(client, body.get("user").get("id"))


# Button press to delete item from meal plan
@app.action('delete_item_from_mp')
def delete_item_from_mp(ack, say, body, logger, client):
    ack()

    item_id = (body.get("actions")[0].get("value")).split("_")[0]
    date = (body.get("actions")[0].get("value")).split("_")[1]
    delete_response = delete_item_from_meal_plan(item_id)

    g_logger.debug(f"Delete meal plan item response: {delete_response}")

    publish_meal_plan_detail_home_view(client, body.get("user").get("id"), date)


# # # # # # # # # # # # # # # # # #
# #    LISTENING TO OPTIONS     # #
# # # # # # # # # # # # # # # # # #


@app.options("home_shop_list_search_ingred_action")
def home_shop_list_ingredient_search(ack, payload):
    search_response = search_all_ingredients(payload.get("value"))
    g_logger.debug(f"Home shop list search results for {payload.get('value')}: {search_response.get('results')}")
    options = []

    for result in search_response.get("results"):
        options.append({
            "text": {
                "type": "plain_text",
                "text": result.get("name")
            },
            "value": str(result.get("id"))
        })

    ack(options=options)


@app.options("ingred_multi_select")
def multi_select_ingredient_search(ack, payload):
    search_response = search_all_ingredients(payload.get("value"))
    g_logger.debug(f"Multi-select search results for {payload.get('value')}: {search_response.get('results')}")
    options = []

    for result in search_response.get("results"):
        options.append({
            "text": {
                "type": "plain_text",
                "text": result.get("name")
            },
            "value": result.get("name")
        })

    ack(options=options)


@app.options("ingred_nutrient_select")
def handle_some_options(ack, payload):
    search_response = search_all_ingredients(payload.get("value"))
    g_logger.debug(f"Select search results for {payload.get('value')}: {search_response.get('results')}")
    options = []

    for result in search_response.get("results"):
        options.append({
            "text": {
                "type": "plain_text",
                "text": result.get("name")
            },
            "value": str(result.get("id"))
        })

    ack(options=options)


# # # # # # # # # # # # # # # # # #
# #      START THE APP          # #
# # # # # # # # # # # # # # # # # #


SlackRequestHandler.clear_all_log_handlers()
logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)


def handler(event, context):
    slack_handler = SlackRequestHandler(app=app)
    return slack_handler.handle(event, context)

# Start the app - for local dev
# if __name__ == "__main__":
# app.start(port=int(os.environ.get("PORT", 3000)))
