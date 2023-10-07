import openai
import mysql.connector
import base64

# Initialize OpenAI API with your API key
openai.api_key = "YOUR_OPENAI_API_KEY"

# Function to paraphrase user input using OpenAI's API
def paraphrase_text(text):
    response = openai.Completion.create(
        engine="text-davinci-002",
        prompt=f"Paraphrase the following text: {text}",
        max_tokens=50  # Adjust this as needed
    )
    return response.choices[0].text.strip()

# Function to calculate similarity percentage between two texts using OpenAI's API
def calculate_similarity(text1, text2):
    response = openai.Completion.create(
        engine="davinci",
        prompt=f"Calculate similarity between:\n{text1}\n{text2}\n",
        max_tokens=1  # Use the whole output
    )
    similarity = float(response.choices[0].text.strip())
    return similarity

# Function to save user input and paraphrased text (and PDF) to the MySQL database
def save_to_directory3(user_input, paraphrased_text, pdf_data):
    connection = mysql.connector.connect(
        host="Kanishk",
        user="root@localhost",
        password="kanishk",
        database="user_database"
    )
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS user_data (original_text TEXT, paraphrased_text TEXT, pdf_data BLOB)")
    cursor.execute("INSERT INTO user_data (original_text, paraphrased_text, pdf_data) VALUES (%s, %s, %s)", (user_input, paraphrased_text, pdf_data))
    connection.commit()
    cursor.close()
    connection.close()

# Function to find the most similar row in database1 and return its first column value
def find_most_similar(user_input):
    connection = mysql.connector.connect(
        host="Kanishk",
        user="root@localhost",
        password="kanishk",
        database="yourdatabasename"
    )
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS data (text TEXT)")
    cursor.execute("SELECT text FROM data")
    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    best_similarity = 0
    best_match = ""

    for row in rows:
        similarity = calculate_similarity(user_input, row[0])
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = row[0]

    return best_match

# Function to search for a value in database2 and return corresponding data
def search_in_database2(value):
    connection = mysql.connector.connect(
        host="Kanishk",
        user="root@localhost",
        password="kanishk",
        database="lawyers_database"
    )
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS lawyers (name TEXT, information TEXT, cases TEXT, calendly_link TEXT)")
    cursor.execute("SELECT * FROM lawyers WHERE name=%s", (value,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()

    if row:
        return row[1], row[2], row[3]
    else:
        return None, None, None

# Main function
def main():
    user_input = input("Enter your text: ")
    user_pdf_path = input("Enter path to PDF file (optional): ")

    # Paraphrase user input
    paraphrased_text = paraphrase_text(user_input)

    # Read and encode the PDF file as binary data
    pdf_data = None
    if user_pdf_path:
        with open(user_pdf_path, "rb") as pdf_file:
            pdf_data = base64.b64encode(pdf_file.read())

    # Save user input, paraphrased text, and PDF to directory3
    save_to_directory3(user_input, paraphrased_text, pdf_data)

    # Find the most similar value in database1
    most_similar_value = find_most_similar(user_input)

    # Search for the value in database2 and get corresponding data
    lawyer_info, lawyer_cases, calendly_link = search_in_database2(most_similar_value)

    if lawyer_info:
        print("Information of the lawyer:", lawyer_info)
        print("Past cases of the lawyer:", lawyer_cases)
        print("Calendly link of the lawyer:", calendly_link)
    else:
        print("No matching lawyer found in database2.")

if __name__ == "__main__":
    main()
