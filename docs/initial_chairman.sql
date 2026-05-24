-- Run ONCE to create the initial Barangay Chairman account.
-- BEFORE RUNNING: replace the values marked with <CHANGE THIS>

INSERT INTO Users (
    Username,
    Password,
    Firstname,
    Lastname,
    ContactNo,
    user_type_id,
    role_id,
    position_id,
    is_verified,
    is_active,
    is_first_login,
    is_password_changed
) VALUES (
    'TestChairman',                          -- <CHANGE THIS> username
    '$2b$12$fewpl.2b5nks.AgApY4dk.Olqui2SnsA9ivd1bra20NRer0i4RPQe',            -- <CHANGE THIS> bcrypt hash from Django shell
    'Tam',                                -- <CHANGE THIS> first name
    'Radaza',                           -- <CHANGE THIS> last name
    '09950323069',                         -- <CHANGE THIS> contact number
    (SELECT UserTypeID FROM UserTypes WHERE type_name = 'Admin'),
    (SELECT RoleID    FROM Roles      WHERE RoleName  = 'Barangay Chairman'),
    (SELECT PositionID FROM Positions WHERE Name      = 'Punong Barangay'),
    1,   -- is_verified
    1,   -- is_active
    1,   -- is_first_login  (forces password change on first login)
    0    -- is_password_changed
);