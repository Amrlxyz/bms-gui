
def filter_can_messages(input_file, output_file):
    target_ids = {"1806E5F4x", "18FF50E5x"}

    with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
        for line in infile:
            parts = line.strip().split()
            # Ensure the line has at least 4 parts and one of them is the target ID
            if len(parts) >= 4 and parts[2] in target_ids:
                outfile.write(line)

if __name__ == "__main__":
    input_filename = "logs/can_log_20250707_164927.asc"      # Replace with your input file name
    output_filename = "filtered_log.txt"  # Output file
    filter_can_messages(input_filename, output_filename)
