#include <stdlib.h>
#include <string.h>

size_t home_path_bad(void) {
    /* getenv returns NULL when the variable is not set */
    const char *home = getenv("HOME");
    return strlen(home);
}
