def trap(height):
    n = len(height)
    if n < 3:
        return 0

    left = 0
    right = n - 1

    left_max = height[left]
    right_max = height[right]

    ans = 0

    while left < right:
        if left_max <= right_max:
            left += 1
            left_max = max(left_max, height[left])
            ans += left_max - height[left]
        else:
            right -= 1
            right_max = max(right_max, height[right])
            ans += right_max - height[right]

    return ans


if __name__ == "__main__":
    height = [0,1,0,2,1,0,1,3,2,1,2,1]
    print(trap(height))
