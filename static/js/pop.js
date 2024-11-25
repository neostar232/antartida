function openNewWindow() {
    // Define the window size
    var width = 800;
    var height = 600;

    // Calculate the position to center the window
    var leftPosition = (screen.width - width) / 2;
    var topPosition = (screen.height - height) / 2;

    // Open a new window with specified size and centered
    window.open('', 'newWindow', 'width=' + width + ', height=' + height + ', left=' + leftPosition + ', top=' + topPosition);
}