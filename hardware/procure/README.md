# procure

The parts list as data, and a tool that puts it in your Amazon cart.

    hardware/.venv/bin/python -m pip install playwright python-dotenv
    hardware/.venv/bin/python -m playwright install chromium
    cp hardware/procure/.env.example hardware/procure/.env

    procure list                  # what the current build needs, with status
    procure cart-url              # one link that adds everything to your cart
    procure login                 # open a browser; sign in once; close it
    procure sync                  # remove what is not on the list, add what is
    procure arrived <id> k=v ...  # mark a part arrived, record its measurements

`procure` is `hardware/.venv/bin/python hardware/procure/procure.py`.

## How it touches your account

It does not know your password and has nowhere to put one. `login` opens a
Chromium window on a profile directory of its own; you sign in the way you
always do, including any code Amazon sends you; the profile keeps the
session, the way your normal browser does. `sync` reuses that profile. If
you want it gone, delete the directory.

`cart-url` needs no browser of its own: Amazon accepts a URL that adds a
list of ASINs and quantities to the cart of whoever opens it. On Amazon.sa
it asks you to sign in first, then adds them. It cannot remove things,
which is what `sync` is for.

`sync` reads the cart page's own markup to find what is in it, and Amazon
changes that markup without notice. Run `sync --dry-run` first; it prints
what it would remove and add and touches nothing. If it lists the cart as
empty when it is not, the selectors in `read_cart` need updating.

Nothing here buys anything. The cart is left for you to check out.

## The data

`parts.json` is the registry. Each part says what it is for, which vehicle,
where it comes from (an ASIN, or a URL for the things Amazon.sa does not
sell), how many, the price seen and when, and its status: `wanted`,
`ordered`, `arrived`, `measured`. Parts that gate a print say which
parameters they gate, and `arrived` asks for them.

`sync` treats the registry as the truth: anything in the cart that is not
a `wanted` part with an ASIN is removed. Add a `keep` list in `.env` if
there are things in the cart that are not this project's.
