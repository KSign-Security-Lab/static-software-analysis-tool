#include <stdlib.h>
#include <string.h>

size_t home_path_bad(void) {
    const char *home = getenv("HOME");
    return strlen(home);
}
