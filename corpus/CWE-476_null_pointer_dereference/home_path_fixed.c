#include <stdlib.h>
#include <string.h>

size_t home_path_fixed(void) {
    const char *home = getenv("HOME");
    if (home == NULL) return 0;
    return strlen(home);
}
