#include <iostream>
#include <string>
#include <algorithm>

// 函数声明
std::string addStrings(const std::string& a, const std::string& b);

int main() {
    // 示例输入
    std::string a = "12345678901234567890";
    std::string b = "98765432109876543210";

    // 调用函数并输出结果
    std::string result = addStrings(a, b);
    std::cout << "Result: " << result << std::endl;

    return 0;
}

// 函数定义
std::string addStrings(const std::string& a, const std::string& b) {
    std::string result;
    int carry = 0;
    int i = a.size() - 1;
    int j = b.size() - 1;

    // 从字符串的末尾开始逐位相加
    while (i >= 0 || j >= 0 || carry > 0) {
        int sum = carry;
        if (i >= 0) sum += a[i--] - '0';
        if (j >= 0) sum += b[j--] - '0';

        // 将相加结果的个位数添加到结果字符串的开头
        result.push_back('0' + (sum % 10));
        carry = sum / 10;
    }

    // 去除结果字符串前导的零
    while (result.size() > 1 && result.back() == '0') {
        result.pop_back();
    }

    // 由于是从低位到高位添加的，所以需要反转结果字符串
    std::reverse(result.begin(), result.end());

    return result;
}