#include <string.h>

void copy_label_fixed(const char *in) {
    /* bounded, and terminated explicitly because strncpy may not */
    char label[16];
    strncpy(label, in, sizeof(label) - 1);
    label[sizeof(label) - 1] = '\0';
    use(label);
}
