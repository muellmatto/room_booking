from os import getenv
username = getenv("username", "admin")
password = getenv("password", "admin")
secret_key = getenv("secret_key", "usrhgcneiuhnceiurnhwo87ghuwhcngniwgh")
imap_host= getenv("imap_host", "woof.woof") 
imap_port = int(getenv("imap_port" ,"993"))
allowed_domain = getenv("allowed_domain", "woof.woof")
production_url = getenv("production_url", "localhost:8000")
