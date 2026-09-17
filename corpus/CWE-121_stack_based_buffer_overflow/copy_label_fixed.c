#include <string.h>

void copy_label_fixed(const char *in) {
    char label[16];
    strncpy(label, in, sizeof(label) - 1);
    label[sizeof(label) - 1] = '\0';
    use(label);
}
