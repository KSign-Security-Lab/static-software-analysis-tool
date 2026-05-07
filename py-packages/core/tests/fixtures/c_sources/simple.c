// Simple test C file
#include <stdio.h>
#include <string.h>

void good_function(char *buffer, int size) {
    if (size > 0) {
        strncpy(buffer, "safe", size - 1);
        buffer[size - 1] = '\0';
    }
}

void bad_function(char *buffer) {
    strcpy(buffer, "unsafe");
}

int main() {
    char buf[100];
    good_function(buf, sizeof(buf));
    bad_function(buf);
    return 0;
}

